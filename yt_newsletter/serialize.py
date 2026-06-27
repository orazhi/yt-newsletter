"""JSON (de)serialization for the two-stage CI pipeline.

The unattended GitHub Actions run is split so the untrusted-network work and the
model work live in separate steps:

  Stage 1 (`fetch_only`)  writes `items.json`: trusted video metadata + the raw
                          transcript text per video. No model, no secrets.
  Stage 2 (claude-code-action)  reads `items.json` and writes one notes file per
                          video (`notes/<video_id>.json`) — the study-notes text.
  Stage 3 (`render_notes`)  joins them back into `StudyNotes` and renders HTML.

Defining the on-disk shapes in exactly one place keeps the two stages in sync,
and lets `summarize.py` (the API path) reuse `study_notes_from_dict` so both
paths build `StudyNotes` identically.
"""

from __future__ import annotations

from .models import GlossaryItem, Section, StudyNotes, Video


def video_to_dict(v: Video) -> dict:
    return {
        "video_id": v.video_id,
        "title": v.title,
        "url": v.url,
        "channel": v.channel,
        "published_at": v.published_at,
        "description": v.description,
        "thumbnail_url": v.thumbnail_url,
        "duration_seconds": v.duration_seconds,
    }


def video_from_dict(d: dict) -> Video:
    """Rebuild a Video from items.json. Defensive: tolerates missing keys."""
    vid = str(d.get("video_id", ""))
    return Video(
        video_id=vid,
        title=str(d.get("title", "")),
        url=str(d.get("url", "") or f"https://www.youtube.com/watch?v={vid}"),
        channel=str(d.get("channel", "")),
        published_at=str(d.get("published_at", "")),
        description=str(d.get("description", "") or ""),
        thumbnail_url=str(d.get("thumbnail_url", "") or ""),
        duration_seconds=d.get("duration_seconds"),
    )


def study_notes_from_dict(video: Video, data: dict, transcript_found: bool) -> StudyNotes:
    """Build StudyNotes from a notes payload (model structured output).

    Defensive on purpose: every field is optional and coerced, so a partial or
    slightly malformed payload still yields usable notes rather than raising —
    one off video should never sink the whole digest.
    """
    sections = [
        Section(
            heading=str(s.get("heading", "")),
            timestamp=str(s.get("timestamp", "")),
            summary=str(s.get("summary", "")),
            key_points=[p for p in s.get("key_points", []) if isinstance(p, str)],
            details=[d for d in s.get("details", []) if isinstance(d, str)],
        )
        for s in data.get("sections", [])
        if isinstance(s, dict)
    ]
    glossary = [
        GlossaryItem(term=str(g.get("term", "")), definition=str(g.get("definition", "")))
        for g in data.get("glossary", [])
        if isinstance(g, dict) and g.get("term")
    ]
    return StudyNotes(
        video=video,
        hook=str(data.get("hook", "")).strip(),
        tldr=str(data.get("tldr", "")).strip(),
        sections=sections,
        insights=[i for i in data.get("insights", []) if isinstance(i, str)],
        takeaways=[t for t in data.get("takeaways", []) if isinstance(t, str)],
        glossary=glossary,
        references=[r for r in data.get("references", []) if isinstance(r, str)],
        transcript_found=transcript_found,
    )


def item_to_dict(video: Video, transcript_found: bool, transcript_text: str) -> dict:
    """One entry of items.json — the Stage 1 -> Stage 2 handoff."""
    return {
        "video": video_to_dict(video),
        "transcript_found": transcript_found,
        "transcript": transcript_text,
    }
