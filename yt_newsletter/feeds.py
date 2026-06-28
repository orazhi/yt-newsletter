"""The source registry: every place we pull wisdom from, and which beat it serves.

This is the heart of the briefing. Instead of scraping YouTube (IP-blocked from
cloud runners), we follow each creator at their most *accessible* source — an RSS
feed, the arXiv API, Hacker News, or, for the handful of video-only channels, the
YouTube RSS listing (titles + descriptions only, which is unblocked).

Three "beats" mirror why you actually watch these channels:
  ai    — AI / ML / engineering frontier (compound your skills)
  news  — India + world current affairs (be a sharp, un-fooled citizen)
  money — personal finance + life/career wisdom (durable compounding)
and one pointer bucket:
  watch — video-only channels with no text twin; surfaced as a short watchlist
          at the very bottom (what it is + why you might click), never synthesized.

`kind` tells the gatherer how to fetch:
  rss      — generic RSS 2.0 / Atom feed
  arxiv    — the arXiv Atom API (export.arxiv.org/api/query?...)
  hn       — Hacker News front page via the Algolia JSON API
  youtube  — a channel @handle / id, listed via YouTube's RSS (pointer only)

Feed URLs marked "(verify)" are best-effort guesses; the gatherer skips any
source that fails to fetch/parse (logging it), so a wrong URL degrades to "that
source is absent" rather than crashing the run. We confirm/correct them after the
first live run, where the network is normal (this sandbox's egress is blocked).
"""

from __future__ import annotations

from dataclasses import dataclass

_ARXIV = "http://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results=15"


@dataclass(frozen=True)
class Source:
    name: str  # human-readable label shown in citations
    beat: str  # "ai" | "news" | "money" | "watch"
    kind: str  # "rss" | "arxiv" | "hn" | "youtube"
    url: str   # feed URL / API URL / channel handle


# ---------------------------------------------------------------------------
# AI / engineering frontier — your skill-compounding engine. These are the same
# curated newsletters you already trust (The Batch / TLDR sec / Data Elixir) plus
# the primary sources they themselves summarize (arXiv, Hacker News, labs).
# ---------------------------------------------------------------------------
_AI: list[Source] = [
    Source("The Batch (DeepLearning.AI)", "ai", "rss", "https://www.deeplearning.ai/the-batch/rss/"),  # (verify)
    Source("TLDR sec", "ai", "rss", "https://tldrsec.com/feed.xml"),  # (verify)
    Source("Data Elixir", "ai", "rss", "https://dataelixir.com/feed/"),  # (verify)
    Source("arXiv cs.LG (Machine Learning)", "ai", "arxiv", _ARXIV.format(q="cat:cs.LG")),
    Source("arXiv cs.CL (NLP / LLMs)", "ai", "arxiv", _ARXIV.format(q="cat:cs.CL")),
    Source("Hacker News (front page)", "ai", "hn", "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"),
    Source("IBM Research blog", "ai", "rss", "https://research.ibm.com/blog/rss"),  # (verify)
]

# ---------------------------------------------------------------------------
# News & current affairs — text-first newsrooms whose *core* output is the
# written article (the video is secondary). Dedup matters most here.
# ---------------------------------------------------------------------------
_NEWS: list[Source] = [
    Source("The News Minute", "news", "rss", "https://www.thenewsminute.com/feed"),  # (verify)
    Source("Scroll.in", "news", "rss", "https://scroll.in/feed"),  # (verify)
    Source("deKoder", "news", "rss", "https://latest.dekoder.com/feed"),  # (verify)
    Source("Rajdeep Sardesai — Breaking Views", "news", "rss", "https://rajdeepsardesai.net/feed"),  # (verify)
]

# ---------------------------------------------------------------------------
# Money & life wisdom — the durable-frameworks beat. Low frequency on purpose.
# ---------------------------------------------------------------------------
_MONEY: list[Source] = [
    Source("warikoo wanderings", "money", "rss", "https://warikoo.substack.com/feed"),
    Source("The Daily Brief (Zerodha)", "money", "rss", "https://thedailybrief.zerodha.com/feed"),
    Source("upGrad blog", "money", "rss", "https://www.upgrad.com/blog/feed"),  # (verify)
]

# ---------------------------------------------------------------------------
# Watchlist candidates — the YouTube RSS listing (titles + descriptions only,
# unblocked) for ALL 14 of your channels. The synthesis stage surfaces a video
# here ONLY if it covers something NOT already in the text sections above — so
# you get a short "go watch this" list of the genuinely-additive videos, and the
# redundant ones (whose substance is already in the text digest) are dropped.
# This spans both the video-only channels AND the ones that also have a text
# twin (a channel can post a video the text feed doesn't cover).
# ---------------------------------------------------------------------------
_WATCH: list[Source] = [
    # video-only (no text twin)
    Source("Welch Labs", "watch", "youtube", "@WelchLabs"),
    Source("Core Dumped", "watch", "youtube", "@CoreDumpped"),
    Source("Ravish Kumar", "watch", "youtube", "@ravishkumar.official"),
    Source("India Global Review", "watch", "youtube", "@IndiaGlobalReview"),
    Source("Stories That Matter", "watch", "youtube", "@StoriesThatMatterIndia"),
    Source("Jist", "watch", "youtube", "@jistnews"),
    Source("Zero1 by Zerodha", "watch", "youtube", "@Zero1byZerodha"),
    # also have a text twin above — listed only when a video adds something the
    # text feed didn't carry
    Source("upGrad", "watch", "youtube", "@upGrad_edu"),
    Source("deKoder", "watch", "youtube", "@DeKoderAI"),
    Source("Ankur Warikoo", "watch", "youtube", "@warikoo"),
    Source("The News Minute", "watch", "youtube", "@thenewsminute"),
    Source("IBM Technology", "watch", "youtube", "@IBMTechnology"),
    Source("Scroll.in", "watch", "youtube", "@ScrollIn"),
    Source("Rajdeep Sardesai", "watch", "youtube", "@RajdeepSardesaiOfficial"),
]

SOURCES: list[Source] = [*_AI, *_NEWS, *_MONEY, *_WATCH]

# Human-readable beat labels + display order for the rendered email.
BEAT_ORDER: list[str] = ["ai", "news", "money"]
BEAT_LABEL: dict[str, str] = {
    "ai": "AI & Engineering",
    "news": "News & Current Affairs",
    "money": "Money & Life",
    "watch": "On your watchlist",
}


def sources_for(beat: str) -> list[Source]:
    return [s for s in SOURCES if s.beat == beat]
