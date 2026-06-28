"""List a channel's recent uploads via YouTube's RSS feed. No auth, no cookies.

The RSS feed (`/feeds/videos.xml?channel_id=UC...`) is public, needs no
authentication, and dodges the bot-wall that blocks yt-dlp extraction. It
carries everything Tier 1 needs: video id, title, publish time, channel name,
description, and thumbnail. Handles/custom URLs are resolved to a channel_id by
scraping the channel page once.
"""

from __future__ import annotations

import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from .models import Video

# A real browser User-Agent + Accept headers. Many newsletter hosts (Substack,
# and Cloudflare/Fastly-fronted sites like deeplearning.ai) reject the bare
# "compatible; bot" UA with a 403, but serve the same RSS fine to a browser-like
# request. YouTube/arXiv/HN are indifferent, so this only helps.
_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/rss+xml,application/atom+xml,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
_CHANNEL_ID = re.compile(r"UC[\w-]{22}")


def _http_get(url: str, timeout: int = 20, retries: int = 4) -> str:
    """GET a URL as text. Retry transient 5xx/429 and network errors with backoff.

    This flagged-IP environment gets throttled intermittently (an occasional 500
    that succeeds on the next try), so a short backoff makes the routine robust.
    Non-transient statuses (404 etc.) fail fast.
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except HTTPError as e:
            last_exc = e
            # 404 is included because YouTube soft-blocks flagged IPs with a 404
            # on the feeds endpoint (it flips back to 200 on a later try). On a
            # clean IP a real 404 just costs a few bounded retries.
            if e.code not in (404, 429, 500, 502, 503, 504):
                raise  # not transient — don't waste retries
        except (URLError, TimeoutError) as e:
            last_exc = e
        if attempt < retries - 1:
            time.sleep(1.0 * (2**attempt))  # 1s, 2s, 4s
    raise last_exc if last_exc else RuntimeError(f"failed to GET {url}")


def resolve_channel_id(channel: str) -> str | None:
    """Normalize a handle / channel id / URL to a UC... channel id."""
    c = channel.strip()
    if re.fullmatch(r"UC[\w-]{22}", c):
        return c
    m = re.search(r"channel_id=(UC[\w-]{22})", c) or re.search(r"/channel/(UC[\w-]{22})", c)
    if m:
        return m.group(1)

    # Otherwise treat it as a handle / custom URL and scrape the page once.
    if c.startswith(("http://", "https://")):
        page_url = c
    elif c.startswith("@"):
        page_url = f"https://www.youtube.com/{c}"
    else:
        page_url = f"https://www.youtube.com/@{c}"
    try:
        html = _http_get(page_url)
    except Exception:
        return None
    # Order matters: "channelId" can point at a *related* channel embedded in the
    # page, so prefer the page-owner signals (externalId / canonical / meta) and
    # keep "channelId" as a last resort.
    for pat in (
        r'"externalId":"(UC[\w-]{22})"',
        r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})">',
        r'<meta itemprop="(?:channelId|identifier)" content="(UC[\w-]{22})">',
        r'/channel/(UC[\w-]{22})',
        r'"channelId":"(UC[\w-]{22})"',
    ):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_feed(
    xml_text: str, max_videos: int = 10, since: datetime | None = None, fallback_channel: str = ""
) -> list[Video]:
    """Parse a YouTube RSS feed string into Video entries (pure; unit-testable)."""
    root = ET.fromstring(xml_text)
    feed_author = root.findtext("atom:title", default=fallback_channel, namespaces=_NS)

    videos: list[Video] = []
    for entry in root.findall("atom:entry", _NS):
        vid = entry.findtext("yt:videoId", namespaces=_NS)
        if not vid:
            continue
        title = entry.findtext("atom:title", default="", namespaces=_NS) or ""
        published = entry.findtext("atom:published", default="", namespaces=_NS) or ""
        author = (
            entry.findtext("atom:author/atom:name", default=feed_author, namespaces=_NS)
            or feed_author
        )
        description, thumbnail = "", ""
        group = entry.find("media:group", _NS)
        if group is not None:
            description = group.findtext("media:description", default="", namespaces=_NS) or ""
            thumb_el = group.find("media:thumbnail", _NS)
            if thumb_el is not None:
                thumbnail = thumb_el.get("url", "")

        videos.append(
            Video(
                video_id=vid,
                title=title,
                url=f"https://www.youtube.com/watch?v={vid}",
                channel=author,
                published_at=published,
                description=description,
                thumbnail_url=thumbnail,
            )
        )

    # Newest first, then apply the `since` cutoff and the count cap.
    videos.sort(key=lambda v: v.published_at, reverse=True)
    if since is not None:
        kept = []
        for v in videos:
            published_dt = _parse_iso(v.published_at)
            if published_dt is None or published_dt >= since:
                kept.append(v)
        videos = kept
    return videos[:max_videos]


def list_recent_videos(
    channel: str, max_videos: int = 10, since_iso: str | None = None
) -> list[Video]:
    """Return recent Video entries for a channel, newest first, filtered by `since`."""
    channel_id = resolve_channel_id(channel)
    if not channel_id:
        return []
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        xml_text = _http_get(feed_url)
    except Exception:
        return []
    return parse_feed(
        xml_text,
        max_videos=max_videos,
        since=_parse_iso(since_iso),
        fallback_channel=channel,
    )
