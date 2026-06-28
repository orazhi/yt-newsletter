"""Stage 1 of the CI pipeline: fetch recent uploads + transcripts -> items.json.

Deterministic. No model, no API key, no secrets — just the unauthenticated RSS
and transcript endpoints. The claude-code-action stage reads items.json and
writes the study notes; `render_notes` turns those into HTML. Splitting it this
way keeps the cheap, untrusted-network work isolated from the paid model step.

    python -m yt_newsletter.fetch_only --since <ISO-8601> --out items.json

Exit codes:
  0  ran fine (items.json written; may contain 0 items on a quiet night)
  2  misconfiguration — no channels configured at all (fail loud, don't email)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from . import serialize, sources, transcript
from .config import Config


def _default_since() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def collect_items(since_iso: str, cfg: Config, max_transcript_chars: int) -> list[dict]:
    """Resolve each channel's recent uploads and attach transcripts."""
    items: list[dict] = []
    seen: set[str] = set()
    for channel in cfg.channels:
        videos = sources.list_recent_videos(
            channel, max_videos=cfg.max_videos_per_channel, since_iso=since_iso
        )
        print(f"[fetch] {channel}: {len(videos)} new video(s)", file=sys.stderr)
        for video in videos:
            if video.video_id in seen:
                continue
            seen.add(video.video_id)
            segments = transcript.get_segments(video.video_id)
            found = bool(segments)
            text = (
                transcript.to_timestamped_text(segments, max_transcript_chars)
                if segments
                else ""
            )
            lang = segments[0].language if segments else ""
            tag = f"transcript::{lang}" if found else "no-transcript"
            print(f"[fetch]   {video.video_id} ({tag}): {video.title[:60]}", file=sys.stderr)
            items.append(serialize.item_to_dict(video, found, text, lang))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 1: fetch videos + transcripts into items.json (no model)."
    )
    parser.add_argument(
        "--since",
        default=_default_since(),
        help="ISO-8601 cutoff; only videos published after this are kept (default: last 24h).",
    )
    parser.add_argument("--out", default="items.json", help="Output path (default: items.json).")
    parser.add_argument(
        "--transcript-chars",
        type=int,
        default=None,
        help="Override max transcript characters per video (default: from config).",
    )
    args = parser.parse_args()

    cfg = Config()
    if not cfg.channels:
        # No channels at all is a misconfiguration, not a quiet night — fail loud
        # so the workflow goes red instead of silently emailing nothing.
        print(
            "[fetch] ERROR: no channels configured. Set the YT_NEWSLETTER_CHANNELS "
            "repo variable (comma-separated) or commit config/channels.txt locally.",
            file=sys.stderr,
        )
        sys.exit(2)

    max_chars = args.transcript_chars or cfg.max_transcript_chars
    items = collect_items(args.since, cfg, max_chars)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"[fetch] wrote {len(items)} item(s) to {args.out}", file=sys.stderr)

    # Expose the count so the workflow can gate the paid agent + email steps on
    # whether anything is actually new (skip both when count == 0).
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"count={len(items)}\n")
    print(f"ITEM_COUNT: {len(items)}")


if __name__ == "__main__":
    main()
