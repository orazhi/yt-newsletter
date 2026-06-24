"""Tests for RSS feed parsing (offline, no network). Run: python tests/test_sources.py."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yt_newsletter.sources import parse_feed, resolve_channel_id  # noqa: E402

# A minimal YouTube-RSS-shaped document with two entries (newest second, to
# prove sorting), plus a channel-level <published> that must NOT be mistaken for
# an entry timestamp.
_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Test Channel</title>
  <published>2015-03-03T00:00:00+00:00</published>
  <entry>
    <id>yt:video:OLD123</id>
    <yt:videoId>OLD123</yt:videoId>
    <title>An older video</title>
    <author><name>Test Channel</name></author>
    <published>2026-06-10T09:00:00+00:00</published>
    <media:group>
      <media:description>Older description &amp; notes.</media:description>
      <media:thumbnail url="https://i.ytimg.com/vi/OLD123/hq.jpg"/>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:NEW456</id>
    <yt:videoId>NEW456</yt:videoId>
    <title>A newer video</title>
    <author><name>Test Channel</name></author>
    <published>2026-06-20T09:00:00+00:00</published>
    <media:group>
      <media:description>Newer description.</media:description>
      <media:thumbnail url="https://i.ytimg.com/vi/NEW456/hq.jpg"/>
    </media:group>
  </entry>
</feed>
"""


def test_parse_feed_orders_newest_first():
    videos = parse_feed(_FEED)
    assert [v.video_id for v in videos] == ["NEW456", "OLD123"]
    assert videos[0].title == "A newer video"
    assert videos[0].channel == "Test Channel"
    assert videos[0].url == "https://www.youtube.com/watch?v=NEW456"


def test_parse_feed_extracts_metadata():
    v = parse_feed(_FEED)[1]  # OLD123
    assert v.description == "Older description & notes."
    assert v.thumbnail_url.endswith("/OLD123/hq.jpg")
    assert v.published_at == "2026-06-10T09:00:00+00:00"


def test_parse_feed_since_filter():
    since = datetime(2026, 6, 15, tzinfo=timezone.utc)
    videos = parse_feed(_FEED, since=since)
    assert [v.video_id for v in videos] == ["NEW456"]  # OLD123 is before the cutoff


def test_parse_feed_max_videos():
    assert len(parse_feed(_FEED, max_videos=1)) == 1


def test_resolve_channel_id_passthrough():
    # A raw channel id resolves to itself with no network call.
    assert resolve_channel_id("UC" + "x" * 22) == "UC" + "x" * 22
    assert resolve_channel_id("https://www.youtube.com/channel/UC" + "y" * 22) == "UC" + "y" * 22


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
