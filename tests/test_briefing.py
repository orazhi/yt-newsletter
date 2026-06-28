"""Offline tests for the briefing engine (no network, no model).

Covers the parts you most need to trust: that you won't be re-served yesterday's
news (the diff), that the same story from several sources collapses to one entry
(clustering), and that the stdlib feed parsers read RSS/Atom/HN correctly.

Run: python tests/test_briefing.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yt_newsletter import feeds, gather  # noqa: E402
from yt_newsletter.briefing import (  # noqa: E402
    Item,
    build_input,
    canonical_key,
    cluster_similar,
    commit_memory,
    dedup_within,
    items_from_input,
    prune_memory,
    select_new,
)

ok = True


def check(name: str, cond: bool) -> None:
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond


# --- canonical key: tracking params + www + trailing slash collapse ----------
k1 = canonical_key("https://www.x.com/a/b/?utm_source=news&id=9")
k2 = canonical_key("http://x.com/a/b?id=9")
check("canonical key normalizes tracking/www/slash", k1 == k2)
check("titleless url still keys", canonical_key("", "Hello World").startswith("title:"))

# --- dedup within a run ------------------------------------------------------
items = [
    Item("ai", "A", "OpenAI releases model Z", "https://a.com/z?utm_x=1"),
    Item("ai", "B", "Model Z released by OpenAI", "https://b.com/z"),
    Item("ai", "A", "OpenAI releases model Z", "https://a.com/z"),  # dup of #1
    Item("news", "C", "Floods hit Assam districts", "https://c.com/assam"),
]
deduped = dedup_within(items)
check("dedup_within drops exact-key dup", len(deduped) == 3)

# --- clustering same story across sources ------------------------------------
clusters = cluster_similar([i for i in deduped if i.beat == "ai"])
check("cluster_similar merges the same story from 2 sources", len(clusters) == 1)
check("cluster has both sources", len(clusters[0].items) == 2)

# --- the cross-night diff ----------------------------------------------------
memory = {"seen": {canonical_key("https://c.com/assam"): "2026-06-20T00:00:00+00:00"}}
fresh = select_new(deduped, memory)
check("select_new hides a story seen on a previous night", all(i.beat == "ai" for i in fresh))

# --- build_input shape + is_update marking -----------------------------------
payload = build_input(items, memory)
check("build_input groups beats", set(payload["beats"]) == {"ai"})
check("build_input dropped the seen news item", "news" not in payload["beats"])
ai_clusters = payload["beats"]["ai"]
check("build_input clustered ai into one entry", len(ai_clusters) == 1)
check("cluster lists both source urls", len(ai_clusters[0]["sources"]) == 2)

# --- commit then re-select => nothing new ------------------------------------
mem2 = commit_memory(items_from_input(payload), memory)
check(
    "after commit, those items are no longer new",
    all(i.beat != "ai" for i in select_new(dedup_within(items), mem2)),
)

# --- prune drops ancient keys ------------------------------------------------
old = {"seen": {"k": "2000-01-01T00:00:00+00:00"}}
check("prune_memory forgets ancient keys", prune_memory(old)["seen"] == {})

# --- feed parsers against fixtures -------------------------------------------
RSS = """<?xml version='1.0'?><rss version='2.0'><channel><title>Warikoo</title>
<item><title>The 5am myth</title><link>https://warikoo.substack.com/p/5am</link>
<description>&lt;p&gt;Why 5am is &lt;b&gt;not&lt;/b&gt; the point.&lt;/p&gt;</description>
<pubDate>Fri, 27 Jun 2026 04:30:00 GMT</pubDate></item></channel></rss>"""
src = feeds.Source("warikoo", "money", "rss", "x")
ri = gather.parse_feed(RSS, src)
check("RSS parsed one item", len(ri) == 1)
check("RSS title", ri[0].title == "The 5am myth")
check("RSS link", ri[0].url == "https://warikoo.substack.com/p/5am")
check("RSS html stripped from summary", "<b>" not in ri[0].summary and "not the point" in ri[0].summary)
check("RSS pubDate -> ISO", ri[0].published_at.startswith("2026-06-27T04:30:00"))

ATOM = """<feed xmlns='http://www.w3.org/2005/Atom'><entry>
<title>Scaling Laws for Memory</title>
<link href='http://arxiv.org/abs/2506.12345v1' rel='alternate'/>
<summary>We study scaling of memory.</summary>
<published>2026-06-27T10:00:00Z</published></entry></feed>"""
ai = gather.parse_feed(ATOM, feeds.Source("arXiv", "ai", "arxiv", "x"))
check("Atom parsed one entry", len(ai) == 1 and ai[0].url.endswith("2506.12345v1"))
check("Atom published -> ISO", ai[0].published_at.startswith("2026-06-27T10:00:00"))

HN = ('{"hits":[{"title":"Show HN: A tiny db","url":"https://t.io",'
      '"objectID":"42","points":250,"num_comments":80,"created_at":"2026-06-27T09:00:00Z"}]}')
hn = gather.parse_hn(HN, feeds.Source("HN", "ai", "hn", "x"))
check("HN parsed", len(hn) == 1 and "250 points" in hn[0].summary)

# --- since parsing -----------------------------------------------------------
check("_parse_since 36h in the past", gather._parse_since("36h") < datetime.now(timezone.utc))

print("\n" + ("ALL PASSED" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
