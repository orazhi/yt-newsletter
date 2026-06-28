"""Stage 1: pull every source into a deduped, diffed `input.json` for the model.

Deterministic, no model, no secrets. For each source in the registry it fetches
the feed (RSS/Atom), the arXiv API, Hacker News, or a YouTube channel listing,
normalizes everything to `Item`s, removes anything seen on a previous night
(`briefing.select_new`), clusters same-story duplicates, and writes the result
grouped by beat. The synthesis stage reads only this file.

    python -m yt_newsletter.gather --since 3d --memory state/memory.json --out briefing/input.json

Defensive on purpose: a single source failing (bad URL, 404, slow) is logged and
skipped — one dead feed never sinks the night's briefing.

Exit codes:
  0  ran (input.json written; may contain 0 new items on a quiet night)
  2  misconfiguration (no sources at all — should never happen with feeds.py)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import feeds, sources
from .briefing import Item, build_input, load_memory

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Feeds occasionally ship a raw "&" that isn't part of an entity (Scroll.in does)
# or a stray control character — either makes ElementTree raise "not well-formed".
# We repair just those two common breakages and re-parse.
_BARE_AMP_RE = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]*;)")


def _strip_illegal_xml(s: str) -> str:
    """Drop the control chars XML 1.0 forbids (keep tab/newline/CR + all printable)."""
    return "".join(
        ch for ch in s
        if ch in "\t\n\r"
        or 0x20 <= ord(ch) <= 0xD7FF
        or 0xE000 <= ord(ch) <= 0xFFFD
        or ord(ch) >= 0x10000
    )


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _xml_root(xml_text: str) -> ET.Element:
    """Parse XML, repairing the breakages most common in real-world feeds.

    Tries a clean parse first; on failure, strips illegal control chars and
    escapes bare ampersands, then parses again. A still-broken feed re-raises
    ParseError, which the caller logs and skips.
    """
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        repaired = _BARE_AMP_RE.sub("&amp;", _strip_illegal_xml(xml_text))
        return ET.fromstring(repaired)


def _clean(text: str, max_chars: int = 1200) -> str:
    """Strip HTML tags and collapse whitespace for a compact plain-text summary."""
    text = _TAG_RE.sub(" ", text or "")
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_chars]


def _to_iso(value: str) -> str:
    """Normalize an RSS RFC-822 or Atom ISO date string to ISO-8601, best-effort."""
    value = (value or "").strip()
    if not value:
        return ""
    try:  # Atom / ISO
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()
    except ValueError:
        pass
    try:  # RSS pubDate (RFC 822)
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def parse_feed(xml_text: str, source: feeds.Source) -> list[Item]:
    """Parse an RSS 2.0 or Atom feed string into Items (namespace-tolerant, pure)."""
    try:
        root = _xml_root(xml_text)
    except ET.ParseError as e:
        print(f"[gather]   {source.name}: XML parse error: {e}", file=sys.stderr)
        return []

    items: list[Item] = []
    for entry in root.iter():
        if _localname(entry.tag) not in ("item", "entry"):
            continue
        title = link = summary = published = ""
        for child in entry:
            ln = _localname(child.tag)
            txt = (child.text or "").strip()
            if ln == "title" and txt:
                title = txt
            elif ln == "link":
                href = child.get("href")
                # Prefer an explicit alternate link; fall back to the first href/text.
                if href and (child.get("rel") in (None, "alternate") or not link):
                    link = href
                elif txt and not link:
                    link = txt
            elif ln in ("encoded", "description", "summary", "content") and txt and not summary:
                summary = txt
            elif ln in ("published", "pubdate", "date", "updated") and txt and not published:
                published = txt
        if not title:
            continue
        items.append(
            Item(
                beat=source.beat,
                source=source.name,
                title=_clean(title, 300),
                url=link,
                published_at=_to_iso(published),
                summary=_clean(summary),
                kind=source.kind,
            )
        )
    return items


def parse_hn(json_text: str, source: feeds.Source) -> list[Item]:
    """Parse the HN Algolia search response into Items."""
    try:
        hits = json.loads(json_text).get("hits", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    out: list[Item] = []
    for h in hits:
        title = (h.get("title") or "").strip()
        if not title:
            continue
        oid = h.get("objectID", "")
        url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
        pts, ncomments = h.get("points", 0), h.get("num_comments", 0)
        out.append(
            Item(
                beat=source.beat,
                source=source.name,
                title=title,
                url=url,
                published_at=_to_iso(h.get("created_at", "")),
                summary=f"{pts} points, {ncomments} comments on Hacker News.",
                kind="hn",
            )
        )
    return out


def fetch_source(source: feeds.Source, since: datetime) -> list[Item]:
    """Fetch + parse one source into Items newer than `since`. Never raises."""
    try:
        if source.kind == "youtube":
            vids = sources.list_recent_videos(source.url, max_videos=4, since_iso=since.isoformat())
            items = [
                Item(beat="watch", source=source.name, title=v.title, url=v.url,
                     published_at=v.published_at, summary=_clean(v.description, 400), kind="youtube")
                for v in vids
            ]
        elif source.kind == "hn":
            items = parse_hn(sources._http_get(source.url), source)
        else:  # rss / arxiv are both XML feeds
            items = parse_feed(sources._http_get(source.url), source)
    except Exception as e:  # noqa: BLE001 — one bad source must not sink the run
        print(f"[gather]   {source.name}: SKIP ({type(e).__name__}: {e})", file=sys.stderr)
        return []

    kept = [it for it in items if _within(it.published_at, since)]
    print(f"[gather]   {source.name}: {len(kept)} recent item(s)", file=sys.stderr)
    return kept


def _within(published_iso: str, since: datetime) -> bool:
    if not published_iso:
        return True  # undated → keep; the memory diff still prevents repeats
    try:
        dt = datetime.fromisoformat(published_iso)
    except ValueError:
        return True
    return dt >= since


def _parse_since(spec: str) -> datetime:
    """Accept '3d', '36h', or an ISO timestamp; default 3 days back."""
    now = datetime.now(timezone.utc)
    spec = (spec or "").strip()
    m = re.fullmatch(r"(\d+)([dh])", spec)
    if m:
        n = int(m.group(1))
        return now - (timedelta(days=n) if m.group(2) == "d" else timedelta(hours=n))
    try:
        dt = datetime.fromisoformat(spec.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return now - timedelta(days=3)


def collect(since: datetime) -> list[Item]:
    items: list[Item] = []
    for source in feeds.SOURCES:
        items.extend(fetch_source(source, since))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: gather + dedup + diff into input.json")
    parser.add_argument("--since", default="3d", help="Lookback window: '3d', '36h', or ISO (default 3d).")
    parser.add_argument("--memory", default="state/memory.json", help="Cross-night memory store.")
    parser.add_argument("--out", default="briefing/input.json", help="Output path for the model input.")
    args = parser.parse_args()

    if not feeds.SOURCES:
        print("[gather] ERROR: no sources configured", file=sys.stderr)
        sys.exit(2)

    since = _parse_since(args.since)
    print(f"[gather] window: since {since.isoformat()} ({len(feeds.SOURCES)} sources)", file=sys.stderr)

    items = collect(since)
    memory = load_memory(Path(args.memory))
    payload = build_input(items, memory)

    n_new = sum(len(c) for c in payload["beats"].values()) + len(payload["watch"])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gather] {len(items)} fetched -> {n_new} new cluster/pointer(s) to {out_path}", file=sys.stderr)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"count={n_new}\n")
    print(f"ITEM_COUNT: {n_new}")


if __name__ == "__main__":
    main()
