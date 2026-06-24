"""Tests for the pure HTML renderer. Run: python tests/test_render.py (or pytest)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yt_newsletter.models import GlossaryItem, Section, StudyNotes, Video  # noqa: E402
from yt_newsletter.render import render_digest, render_subject  # noqa: E402


def _sample_items() -> list[StudyNotes]:
    return [
        StudyNotes(
            video=Video(
                video_id="abc123",
                title="Build a <thing> in Rust",
                url="https://www.youtube.com/watch?v=abc123",
                channel="Coding Channel",
                published_at="2026-06-20T10:00:00+00:00",
                thumbnail_url="https://i.ytimg.com/vi/abc123/hq.jpg",
            ),
            hook="Why ownership clicks once you build this.",
            tldr="A walkthrough of building a thing, with the borrow checker explained.",
            sections=[
                Section(
                    heading="Project setup",
                    timestamp="00:30",
                    summary="Sets up cargo and the module layout.",
                    key_points=["cargo new", "module layout"],
                    details=["uses edition 2021", "single binary crate"],
                ),
                Section(
                    heading="Ownership",
                    timestamp="04:12",
                    summary="Explains moves vs borrows with a concrete example.",
                    key_points=["move semantics", "&T vs &mut T"],
                ),
            ],
            insights=["Ownership is about who frees memory, not who can read it."],
            takeaways=["Reach for borrows before clones."],
            glossary=[GlossaryItem(term="Borrow checker", definition="Compile-time alias checker.")],
            references=["The Rust Book, ch. 4"],
        ),
        StudyNotes(
            video=Video(
                video_id="def456",
                title="No transcript video",
                url="https://www.youtube.com/watch?v=def456",
                channel="Other Channel",
                published_at="2026-06-20T11:00:00+00:00",
            ),
            tldr="Notes from description only.",
            transcript_found=False,
        ),
    ]


def test_render_digest_contains_content():
    doc = render_digest(_sample_items(), "2026-06-21")
    assert "Your YouTube study notes" in doc
    assert "2026-06-21" in doc
    assert "https://www.youtube.com/watch?v=abc123" in doc
    assert "Coding Channel" in doc
    assert "Project setup" in doc
    assert "00:30" in doc
    assert "move semantics" in doc
    assert "uses edition 2021" in doc
    assert "Key insights" in doc
    assert "Borrow checker" in doc
    assert "The Rust Book, ch. 4" in doc


def test_render_marks_missing_transcript():
    doc = render_digest(_sample_items(), "2026-06-21")
    assert "No transcript available" in doc
    assert "Notes from description only." in doc


def test_render_escapes_html():
    doc = render_digest(_sample_items(), "2026-06-21")
    assert "Build a &lt;thing&gt; in Rust" in doc
    assert "<thing>" not in doc


def test_render_empty():
    doc = render_digest([], "2026-06-21")
    assert "No new videos" in doc
    assert "0 video(s)" in doc


def test_subject_line():
    assert render_subject([], "2026-06-21").endswith("nothing new")
    subj = render_subject(_sample_items(), "2026-06-21")
    assert "Build a <thing> in Rust" in subj
    assert "+1 more" in subj


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
