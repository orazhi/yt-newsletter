#!/usr/bin/env python3
"""
fetch_videos.py — Tier 1 content fetcher for the nightly YouTube digest.

Pure, deterministic, no LLM. Given a list of subscribed channels and a cutoff
timestamp, it:

  1. reads each channel's public RSS feed (no auth, not bot-gated) to find
     videos published AFTER the cutoff,
  2. for each new video, extracts metadata + description (reliable) and the
     transcript via yt-dlp subtitles (best-effort; reliable with a PO-token
     provider + www.google.com egress),
  3. writes an items.json bundle for the summarisation/digest steps.

Dedup is stateless: the caller passes --since (the timestamp of the last
newsletter, derived from Gmail). No state is stored on disk. On the first run,
default to the last 24 hours.

Usage:
    python3 fetch_videos.py --channels config/channels.txt \
        --since 2026-06-20T00:00:00Z --out /tmp/yt-newsletter/items.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
WATCH_URL = "https://www.youtube.com/watch?v={vid}"
SYSTEM_CA = "/etc/ssl/certs/ca-certificates.crt"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")

# Path to a Netscape-format cookies.txt used to authenticate yt-dlp (bypasses
# the "confirm you're not a bot" check on cloud IPs). Set in main() from
# --cookies / $YT_COOKIES_FILE / config/cookies.txt. None = unauthenticated.
COOKIES: str | None = None


# --------------------------------------------------------------------------- #
# Environment setup
# --------------------------------------------------------------------------- #
def ensure_certifi() -> None:
    """Point certifi at the system CA bundle.

    The managed egress proxy intercepts TLS with a self-signed CA that lives in
    the system bundle but NOT in certifi's bundle (which yt-dlp uses, ignoring
    SSL_CERT_FILE). Without this, every yt-dlp call fails with
    CERTIFICATE_VERIFY_FAILED. No-op when the bundles already match or when
    there is no system bundle (e.g. a normal laptop).
    """
    try:
        import certifi
    except ImportError:
        return
    target = Path(certifi.where())
    system = Path(SYSTEM_CA)
    if not system.exists():
        return
    try:
        if target.read_bytes() != system.read_bytes():
            target.write_bytes(system.read_bytes())
    except OSError as e:
        print(f"[warn] could not patch certifi bundle: {e}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def parse_iso(ts: str) -> dt.datetime:
    """Parse an ISO-8601 timestamp into an aware UTC datetime."""
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(ts)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --------------------------------------------------------------------------- #
# Channel resolution
# --------------------------------------------------------------------------- #
def read_channels(path: Path) -> list[str]:
    """Read channel identifiers from a file, skipping blanks/comments."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


# Resolve a channel page to its OWNER's id. The page contains many "channelId"
# occurrences (recommended channels, etc.), so prefer the authoritative
# "externalId" and the canonical /channel/ link before falling back.
_CID_PATTERNS = [
    re.compile(r"\"externalId\":\"(UC[0-9A-Za-z_-]{22})\""),
    re.compile(r"rel=\"canonical\" href=\"https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})\""),
    re.compile(r"property=\"og:url\" content=\"https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})\""),
    re.compile(r"\"channelId\":\"(UC[0-9A-Za-z_-]{22})\""),
]
_CID_CACHE: dict[str, str] = {}


def resolve_channel_id(token: str) -> str | None:
    """Resolve a channel token to its UC… channel id.

    Accepts: a bare UC… id, a full channel/handle URL, or an @handle. Handles
    and custom URLs are resolved by scraping the channel page for "channelId".
    """
    token = token.strip()
    if token in _CID_CACHE:
        return _CID_CACHE[token]

    if re.fullmatch(r"UC[0-9A-Za-z_-]{22}", token):
        _CID_CACHE[token] = token
        return token

    # Build a channel URL from the token.
    if token.startswith("http"):
        url = token
    elif token.startswith("@"):
        url = f"https://www.youtube.com/{token}"
    elif token.startswith("UC"):
        url = f"https://www.youtube.com/channel/{token}"
    else:
        url = f"https://www.youtube.com/@{token}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        for pat in _CID_PATTERNS:
            m = pat.search(html)
            if m:
                _CID_CACHE[token] = m.group(1)
                return m.group(1)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not resolve channel '{token}': {e}", file=sys.stderr)
    return None


# --------------------------------------------------------------------------- #
# RSS feed
# --------------------------------------------------------------------------- #
def fetch_feed_entries(channel_id: str) -> list[dict]:
    """Return latest entries for a channel from its RSS feed (newest first).

    The Atom feed carries everything the digest needs — title, description,
    thumbnail, view count, publish time — with NO bot-gated API call, so the
    core digest is reliable even when the egress IP is flagged by YouTube.
    """
    url = RSS_URL.format(cid=channel_id)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    channel_title = root.findtext("a:title", default="", namespaces=NS)
    entries = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        published = e.findtext("a:published", namespaces=NS)
        title = e.findtext("a:title", namespaces=NS)
        if not (vid and published):
            continue
        g = e.find("media:group", NS)
        description = thumbnail = ""
        view_count = None
        if g is not None:
            description = g.findtext("media:description", default="", namespaces=NS) or ""
            t = g.find("media:thumbnail", NS)
            thumbnail = t.get("url") if t is not None else ""
            st = g.find("media:community/media:statistics", NS)
            if st is not None and st.get("views", "").isdigit():
                view_count = int(st.get("views"))
        entries.append({
            "video_id": vid,
            "published": published,
            "title": title,
            "channel": channel_title,
            "channel_id": channel_id,
            "description": description,
            "thumbnail": thumbnail,
            "view_count": view_count,
        })
    return entries


# --------------------------------------------------------------------------- #
# Per-video extraction (metadata + transcript)
# --------------------------------------------------------------------------- #
def _yt_dlp(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    extra = os.environ.get("YT_DLP_EXTRA_ARGS", "")
    cmd = ["yt-dlp", "--no-warnings", "--no-progress"]
    if COOKIES:
        cmd += ["--cookies", COOKIES]
    if extra:
        cmd += extra.split()
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def fetch_metadata(video_id: str) -> dict:
    """Fetch description + core metadata for a video (reliable path)."""
    url = WATCH_URL.format(vid=video_id)
    p = _yt_dlp(["--skip-download", "-J", url], timeout=90)
    if p.returncode != 0 or not p.stdout.strip():
        return {"error": _short_error(p.stderr)}
    d = json.loads(p.stdout)
    thumbs = d.get("thumbnails") or []
    thumb = thumbs[-1]["url"] if thumbs else (d.get("thumbnail") or "")
    return {
        "title": d.get("title"),
        "channel": d.get("channel") or d.get("uploader"),
        "channel_id": d.get("channel_id"),
        "duration": d.get("duration"),
        "view_count": d.get("view_count"),
        "upload_date": d.get("upload_date"),
        "description": d.get("description") or "",
        "thumbnail": thumb,
    }


def fetch_transcript(video_id: str, retries: int = 2) -> tuple[str | None, str]:
    """Fetch a transcript via yt-dlp subtitles. Returns (text, source).

    source is one of: manual, auto, none:<reason>. Best-effort: on a datacenter
    IP without a PO-token provider this fails for some videos; the caller keeps
    the description as a fallback.
    """
    url = WATCH_URL.format(vid=video_id)
    last_reason = "unknown"
    for attempt in range(retries + 1):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "%(id)s.%(ext)s")
            p = _yt_dlp([
                "--skip-download", "--write-subs", "--write-auto-subs",
                "--sub-langs", "en.*", "--sub-format", "vtt",
                "-o", out, url,
            ], timeout=120)
            vtts = sorted(Path(tmp).glob(f"{video_id}*.vtt"))
            if vtts:
                # Prefer a manually-authored track over the auto one.
                manual = [f for f in vtts if "-orig" not in f.name
                          and "auto" not in f.name.lower()]
                chosen = manual[0] if manual else vtts[0]
                text = vtt_to_text(chosen.read_text(encoding="utf-8", errors="replace"))
                if text:
                    source = "manual" if chosen in manual else "auto"
                    return text, source
            last_reason = _short_error(p.stderr) or "no subtitles"
            if "sign in to confirm" in last_reason.lower() and attempt < retries:
                continue
            if "no subtitle" in last_reason.lower() or "available" in last_reason.lower():
                break
    return None, f"none:{last_reason}"


_TAG_RE = re.compile(r"<[^>]+>")
_TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->")


def vtt_to_text(vtt: str) -> str:
    """Convert WEBVTT (incl. rolling auto-captions) to clean, de-duplicated text."""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if (not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE"))
                or _TS_RE.match(line) or "-->" in line or line.isdigit()):
            continue
        line = _TAG_RE.sub("", line).strip()
        if not line:
            continue
        # Collapse the rolling-caption repetition: skip if identical to the last
        # emitted line, or if the last line is a prefix this one extends.
        if lines:
            if line == lines[-1]:
                continue
            if line.startswith(lines[-1]):
                lines[-1] = line
                continue
        lines.append(line)
    return " ".join(lines).strip()


def _short_error(stderr: str) -> str:
    for ln in (stderr or "").splitlines():
        if "ERROR" in ln or "error" in ln:
            return ln.strip()[:200]
    return (stderr or "").strip().splitlines()[-1][:200] if stderr.strip() else ""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channels", type=Path, default=Path("config/channels.txt"),
                    help="file with one channel id/@handle/URL per line")
    ap.add_argument("--since", default=None,
                    help="ISO-8601 cutoff; include videos published after this. "
                         "Default: 24h ago (first-run behaviour).")
    ap.add_argument("--out", type=Path, default=Path("/tmp/yt-newsletter/items.json"))
    ap.add_argument("--max-per-channel", type=int, default=10,
                    help="safety cap on videos considered per channel")
    ap.add_argument("--no-transcript", action="store_true",
                    help="skip transcript extraction (RSS metadata + description only)")
    ap.add_argument("--rich", action="store_true",
                    help="also fetch full metadata via yt-dlp -J (duration, full "
                         "description). Needs cookies/PO-token on flagged IPs; the "
                         "default RSS-only path is more reliable.")
    ap.add_argument("--cookies", default=None,
                    help="path to a Netscape cookies.txt to authenticate yt-dlp "
                         "(bypasses YouTube's bot check). Defaults to "
                         "$YT_COOKIES_FILE, else config/cookies.txt if present.")
    args = ap.parse_args(argv)

    ensure_certifi()

    # Resolve the cookies file: --cookies > $YT_COOKIES_FILE > config/cookies.txt.
    global COOKIES
    candidate = (args.cookies or os.environ.get("YT_COOKIES_FILE")
                 or "config/cookies.txt")
    if candidate and Path(candidate).is_file() and Path(candidate).stat().st_size > 0:
        COOKIES = candidate
        print(f"[info] using cookies: {COOKIES}", file=sys.stderr)
    elif args.cookies or os.environ.get("YT_COOKIES_FILE"):
        print(f"[warn] cookies file not found/empty: {candidate} — "
              f"transcripts will be best-effort", file=sys.stderr)
    else:
        print("[info] no cookies file — transcripts best-effort "
              "(see ROUTINE.md)", file=sys.stderr)

    cutoff = parse_iso(args.since) if args.since else now_utc() - dt.timedelta(hours=24)
    print(f"[info] cutoff: {cutoff.isoformat()}  (videos published after this)",
          file=sys.stderr)

    if not args.channels.exists():
        print(f"[error] channels file not found: {args.channels}\n"
              f"        copy config/channels.example.txt and add your channels.",
              file=sys.stderr)
        return 2
    tokens = read_channels(args.channels)
    print(f"[info] {len(tokens)} channel(s) configured", file=sys.stderr)

    # 1. Resolve channels and collect new videos from RSS.
    new_videos: list[dict] = []
    for token in tokens:
        cid = resolve_channel_id(token)
        if not cid:
            continue
        try:
            entries = fetch_feed_entries(cid)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] feed failed for {token} ({cid}): {e}", file=sys.stderr)
            continue
        kept = [e for e in entries[:args.max_per_channel]
                if parse_iso(e["published"]) > cutoff]
        if kept:
            print(f"[info] {token}: {len(kept)} new", file=sys.stderr)
        new_videos.extend(kept)

    # Newest first across all channels.
    new_videos.sort(key=lambda e: parse_iso(e["published"]), reverse=True)
    print(f"[info] {len(new_videos)} new video(s) total; extracting content…",
          file=sys.stderr)

    # 2. Build each item from the reliable RSS data, then best-effort enrich
    #    with full metadata (--rich) and the transcript.
    items = []
    for i, v in enumerate(new_videos, 1):
        vid = v["video_id"]
        print(f"[info] ({i}/{len(new_videos)}) {vid} {v['title'][:60]}", file=sys.stderr)
        item = {
            "video_id": vid,
            "url": WATCH_URL.format(vid=vid),
            "title": v["title"],
            "channel": v["channel"],
            "channel_id": v["channel_id"],
            "published": v["published"],
            "duration": None,
            "view_count": v.get("view_count"),
            "thumbnail": v.get("thumbnail", ""),
            "description": v.get("description", ""),
            "transcript": None,
            "transcript_source": "skipped",
        }
        if args.rich:
            meta = fetch_metadata(vid)
            if meta.get("error"):
                item["meta_error"] = meta["error"]
            else:
                item["duration"] = meta.get("duration")
                item["title"] = meta.get("title") or item["title"]
                item["channel"] = meta.get("channel") or item["channel"]
                if meta.get("description"):
                    item["description"] = meta["description"]
                if meta.get("thumbnail"):
                    item["thumbnail"] = meta["thumbnail"]
                if meta.get("view_count") is not None:
                    item["view_count"] = meta["view_count"]
        if not args.no_transcript:
            text, source = fetch_transcript(vid)
            item["transcript"] = text
            item["transcript_source"] = source
        items.append(item)

    # 3. Write the bundle.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "generated_at": now_utc().isoformat(),
        "cutoff": cutoff.isoformat(),
        "count": len(items),
        "items": items,
    }
    args.out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    with_tx = sum(1 for it in items if it["transcript"])
    print(f"[done] wrote {len(items)} item(s) to {args.out} "
          f"({with_tx} with transcript)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
