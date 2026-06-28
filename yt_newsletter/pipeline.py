"""Orchestrate fetch -> transcript -> deep notes -> render into an HTML file."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from . import render, sources, summarize, transcript
from .config import Config
from .models import StudyNotes


def build_notes(since_iso: str | None, config: Config | None = None) -> list[StudyNotes]:
    """Collect and deeply summarize everything published since `since_iso`."""
    cfg = config or Config()
    if not cfg.channels:
        print("[warn] no channels configured (config/channels.txt)", file=sys.stderr)
        return []

    import anthropic

    client = anthropic.Anthropic()

    items: list[StudyNotes] = []
    seen: set[str] = set()
    for channel in cfg.channels:
        videos = sources.list_recent_videos(
            channel, max_videos=cfg.max_videos_per_channel, since_iso=since_iso
        )
        print(f"[info] {channel}: {len(videos)} new video(s)", file=sys.stderr)
        for video in videos:
            if video.video_id in seen:
                continue
            seen.add(video.video_id)
            segments = transcript.get_segments(video.video_id)
            tag = "transcript" if segments else "no-transcript"
            print(f"[info]   summarizing {video.video_id} ({tag}): {video.title[:60]}",
                  file=sys.stderr)
            items.append(
                summarize.deep_study_notes(
                    client,
                    video,
                    segments or [],
                    model=cfg.model,
                    max_tokens=cfg.max_summary_tokens,
                    effort=cfg.effort,
                    max_transcript_chars=cfg.max_transcript_chars,
                )
            )
    return items


def run(since_iso: str | None, out_path: str, config: Config | None = None) -> tuple[str, str]:
    """Build the digest, write HTML to out_path, return (out_path, subject)."""
    items = build_notes(since_iso, config)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html_doc = render.render_digest(items, date)
    subject = render.render_subject(items, date)
    Path(out_path).write_text(html_doc, encoding="utf-8")
    return out_path, subject
