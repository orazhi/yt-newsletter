"""Stage 3 of the CI pipeline: join items.json + agent notes -> digest.html.

Trusted video metadata (title, URL, channel, publish time) comes from
`items.json`, which Stage 1 produced. The study-notes text comes from the
per-video files the model wrote (`notes/<video_id>.json`). We join on video_id,
so the model only ever contributes notes content — it cannot alter the title,
URL, or channel that end up in your inbox. Rendering reuses the unit-tested
`render.render_digest`.

    python -m yt_newsletter.render_notes --items items.json --notes-dir notes --out digest.html
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import render, serialize
from .models import StudyNotes


def _load_notes(notes_dir: Path, video_id: str) -> dict | None:
    """Load one agent-written notes file, or None if missing/unparseable."""
    path = notes_dir / f"{video_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def build_study_notes(items: list[dict], notes_dir: Path) -> list[StudyNotes]:
    notes: list[StudyNotes] = []
    for entry in items:
        video = serialize.video_from_dict(entry.get("video", {}))
        transcript_found = bool(entry.get("transcript_found"))
        data = _load_notes(notes_dir, video.video_id)
        if data is None:
            # Missing/invalid notes for one video shouldn't sink the digest:
            # render a placeholder card and keep going.
            print(
                f"[render] WARN: no usable notes for {video.video_id} "
                f"({video.title[:50]}); rendering placeholder",
                file=sys.stderr,
            )
            notes.append(
                StudyNotes(
                    video=video,
                    tldr="(Study notes could not be generated for this video.)",
                    transcript_found=transcript_found,
                )
            )
            continue
        notes.append(serialize.study_notes_from_dict(video, data, transcript_found))
    return notes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 3: render items.json + notes/ into a digest HTML file."
    )
    parser.add_argument("--items", default="items.json", help="Stage 1 items.json path.")
    parser.add_argument("--notes-dir", default="notes", help="Directory of <video_id>.json files.")
    parser.add_argument("--out", default="digest.html", help="Output HTML path.")
    args = parser.parse_args()

    items = json.loads(Path(args.items).read_text(encoding="utf-8"))
    # items.json is newest-first per channel, but channels interleave — sort the
    # merged list by publish time so the digest reads newest-first overall.
    items.sort(key=lambda e: e.get("video", {}).get("published_at", ""), reverse=True)

    notes = build_study_notes(items, Path(args.notes_dir))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html_doc = render.render_digest(notes, date)
    subject = render.render_subject(notes, date)
    Path(args.out).write_text(html_doc, encoding="utf-8")
    print(f"SUBJECT: {subject}")
    print(f"OUT: {args.out}")


if __name__ == "__main__":
    main()
