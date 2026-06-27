"""Fetch a video's transcript with timestamps. No auth, no cookies needed.

Uses youtube_transcript_api, which pulls the caption track YouTube already
serves — this sidesteps the bot-wall that blocks yt-dlp's extraction/download
path. Timestamps are preserved so the summarizer can anchor each section to a
point in the video. Returns None when a video has no usable transcript
(disabled subs, live, music-only); the caller falls back to the description.
"""

from __future__ import annotations

from dataclasses import dataclass

# Preferred caption languages, in order. English variants first; extend as needed.
DEFAULT_LANGUAGES: tuple[str, ...] = ("en", "en-US", "en-GB")


@dataclass
class Segment:
    start: float  # seconds from the start of the video
    text: str


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
    except ImportError:  # dependency not installed
        return None

    langs = list(languages)
    try:
        # youtube_transcript_api >= 1.0 exposes an instance .fetch(); older
        # releases expose the classmethod .get_transcript(). Support both.
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            raw = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
            pairs = [(s.get("start", 0.0), s.get("text", "")) for s in raw]
        else:
            fetched = YouTubeTranscriptApi().fetch(video_id, languages=langs)
            pairs = [(getattr(s, "start", 0.0), getattr(s, "text", "")) for s in fetched]
    except Exception:
        # No transcript, disabled subs, rate-limited, or a transient error.
        return None

    segments = [
        Segment(start=float(start), text=text.strip())
        for start, text in pairs
        if text and text.strip()
    ]
    return segments or None


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
