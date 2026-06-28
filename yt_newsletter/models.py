"""Core data structures shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Video:
    """A single YouTube video and its feed metadata (from the channel RSS listing)."""

    video_id: str
    title: str
    url: str
    channel: str
    published_at: str  # ISO-8601, e.g. "2026-06-20T14:03:00+00:00"
    description: str = ""
    thumbnail_url: str = ""
    duration_seconds: int | None = None
