"""Runtime configuration, from env vars and an optional channels file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Default channel list: config/channels.txt (one channel per line). Gitignored —
# it holds your personal subscription list.
DEFAULT_CHANNELS_FILE = Path(__file__).resolve().parent.parent / "config" / "channels.txt"


def _load_channels(channels_file: Path = DEFAULT_CHANNELS_FILE) -> list[str]:
    """Channels from YT_NEWSLETTER_CHANNELS (comma-sep) or config/channels.txt."""
    env = os.environ.get("YT_NEWSLETTER_CHANNELS", "").strip()
    if env:
        return [c.strip() for c in env.split(",") if c.strip()]
    if channels_file.exists():
        lines = channels_file.read_text(encoding="utf-8").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    return []


@dataclass
class Config:
    channels: list[str] = field(default_factory=_load_channels)
    max_videos_per_channel: int = int(os.environ.get("YT_NEWSLETTER_MAX_PER_CHANNEL", "5"))
    # Default per the claude-api skill: opus-4-8 for the best extraction quality.
    # Set YT_NEWSLETTER_MODEL=claude-haiku-4-5 for a cheaper, high-volume run.
    model: str = os.environ.get("YT_NEWSLETTER_MODEL", "claude-opus-4-8")
    effort: str = os.environ.get("YT_NEWSLETTER_EFFORT", "high")
    # Study notes can be long — give the model room. Streaming avoids timeouts.
    max_summary_tokens: int = int(os.environ.get("YT_NEWSLETTER_MAX_SUMMARY_TOKENS", "16000"))
    # Cap transcript characters fed to the model (keeps cost bounded on long videos).
    max_transcript_chars: int = int(os.environ.get("YT_NEWSLETTER_MAX_TRANSCRIPT_CHARS", "120000"))
