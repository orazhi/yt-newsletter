"""yt_newsletter — a nightly, deduplicated, cited intelligence briefing by email.

Instead of scraping YouTube transcripts (IP-blocked from cloud runners), the
briefing follows each source at its most accessible point — RSS, the arXiv API,
Hacker News, and the YouTube RSS *listing* — then dedups against what it already
sent, clusters the same story across sources, and emails the diff.

Modules:
  feeds        — the source registry (which feed serves which beat)
  gather       — Stage 1: fetch every source, normalize into Items
  briefing     — dedup, cluster, and the cross-night "diff since last night"
  render_brief — turn the synthesized briefing JSON into HTML email
  sources      — YouTube RSS listing + a retrying HTTP helper (reused by gather)
  models       — shared data structures (Video)
"""

__all__ = [
    "feeds",
    "gather",
    "briefing",
    "render_brief",
    "sources",
    "models",
]
