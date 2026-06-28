"""Fetch a video's transcript with timestamps. No auth, no cookies needed.

Uses youtube_transcript_api, which pulls the caption track YouTube already
serves — this sidesteps the bot-wall that blocks yt-dlp's extraction/download
path. Timestamps are preserved so the summarizer can anchor each section to a
point in the video. Returns None when a video has no usable transcript
(disabled subs, live, music-only); the caller falls back to the description.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

DEFAULT_LANGUAGES: tuple[str, ...] = (
    "en", "en-US", "en-GB", "en-IN",
    "hi", "hi-IN",
)


@dataclass
class Segment:
    start: float  # seconds from the start of the video
    text: str
    language: str = ""


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def get_segments(
    video_id: str, languages: tuple[str, ...] = DEFAULT_LANGUAGES
) -> list[Segment] | None:
    """Return timestamped transcript segments for a video id, or None."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print(f"[transcript] {video_id}: youtube-transcript-api not installed", file=sys.stderr)
        return None

    api = YouTubeTranscriptApi()
    langs = list(languages)

    # Step 1: list what's actually available so we can log it.
    available_langs: list[str] = []
    try:
        transcript_list = api.list(video_id)
        available_langs = [t.language_code for t in transcript_list]
    except Exception as e:
        print(f"[transcript] {video_id}: list failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None

    if not available_langs:
        print(f"[transcript] {video_id}: no captions available at all", file=sys.stderr)
        return None

    # Step 2: fetch the best matching transcript.
    matched_lang = ""
    try:
        fetched = api.fetch(video_id, languages=langs)
        pairs = [(getattr(s, "start", 0.0), getattr(s, "text", "")) for s in fetched]
        # Determine which language was actually returned.
        for lang in langs:
            if lang in available_langs:
                matched_lang = lang
                break
    except Exception as e:
        # None of the requested languages matched — try ANY available transcript
        # as a last resort. A transcript in an unexpected language is still better
        # than falling back to description-only.
        print(
            f"[transcript] {video_id}: preferred langs {langs} not in {available_langs}, "
            f"trying fallback to first available",
            file=sys.stderr,
        )
        try:
            fallback_lang = available_langs[0]
            fetched = api.fetch(video_id, languages=[fallback_lang])
            pairs = [(getattr(s, "start", 0.0), getattr(s, "text", "")) for s in fetched]
            matched_lang = fallback_lang
        except Exception as e2:
            print(
                f"[transcript] {video_id}: fallback also failed: {type(e2).__name__}: {e2}",
                file=sys.stderr,
            )
            return None

    segments = [
        Segment(start=float(start), text=text.strip(), language=matched_lang)
        for start, text in pairs
        if text and text.strip()
    ]
    if not segments:
        print(f"[transcript] {video_id}: fetched but all segments empty", file=sys.stderr)
        return None

    print(
        f"[transcript] {video_id}: OK lang={matched_lang} segments={len(segments)}",
        file=sys.stderr,
    )
    return segments


def to_timestamped_text(segments: list[Segment], max_chars: int = 120_000) -> str:
    """Render segments as '[mm:ss] text' lines for the model, capped by length."""
    lines: list[str] = []
    total = 0
    for seg in segments:
        line = f"[{_format_timestamp(seg.start)}] {seg.text}"
        if total + len(line) + 1 > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


def plain_text(segments: list[Segment]) -> str:
    """Concatenate segment text with no timestamps."""
    return " ".join(seg.text for seg in segments)
