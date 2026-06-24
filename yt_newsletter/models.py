"""Core data structures shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Video:
    """A single YouTube video and its feed metadata."""

    video_id: str
    title: str
    url: str
    channel: str
    published_at: str  # ISO-8601, e.g. "2026-06-20T14:03:00+00:00"
    description: str = ""
    thumbnail_url: str = ""
    duration_seconds: int | None = None


@dataclass
class Section:
    """One thematic chunk of the video, anchored to a timestamp."""

    heading: str
    timestamp: str = ""  # "mm:ss" / "h:mm:ss" where this section begins
    summary: str = ""  # detailed prose preserving the reasoning, not just the claim
    key_points: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)  # examples, numbers, specifics


@dataclass
class GlossaryItem:
    term: str
    definition: str


@dataclass
class StudyNotes:
    """Deep, near-complete study notes extracted from a video.

    Detailed enough that a reader gets essentially all the knowledge and wisdom
    of the video without watching it.
    """

    video: Video
    hook: str = ""  # one line: why this video matters
    tldr: str = ""  # a few sentences capturing the core
    sections: list[Section] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)  # the non-obvious "wisdom"
    takeaways: list[str] = field(default_factory=list)  # practical / actionable
    glossary: list[GlossaryItem] = field(default_factory=list)
    references: list[str] = field(default_factory=list)  # people, papers, tools, links
    transcript_found: bool = True  # False → notes built from title/description only
