"""Stage 3: render the model's crafted briefing JSON into an HTML email.

The synthesis stage writes `briefing/output.json`; this turns it into a clean,
inline-CSS email (sections by beat, every claim citation-linked, the video-only
watchlist at the very bottom). All text is HTML-escaped — even though the model
produced it, the underlying material was untrusted, so we never inject raw markup.

    python -m yt_newsletter.render_brief --in briefing/output.json --out briefing.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .feeds import BEAT_LABEL, BEAT_ORDER

_STYLE = """
  body{margin:0;background:#f4f5f7;color:#1a1a1a;
       font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.55}
  .wrap{max-width:680px;margin:0 auto;padding:24px 18px}
  .head{padding:8px 2px 18px}
  .head h1{margin:0;font-size:22px}
  .head .intro{color:#444;font-size:15px;margin-top:6px}
  .beat{margin:26px 0 8px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;
        color:#6b46c1;font-weight:700;border-bottom:2px solid #e7e2f5;padding-bottom:6px}
  .card{background:#fff;border:1px solid #e6e6e9;border-radius:10px;padding:16px 18px;margin:12px 0}
  .card h2{margin:0 0 4px;font-size:17px;line-height:1.3}
  .why{color:#6b46c1;font-size:14px;font-weight:600;margin:2px 0 8px}
  .detail{font-size:14.5px;color:#222;margin:0}
  .badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.04em;
         border-radius:5px;padding:1px 6px;margin-right:7px;vertical-align:2px}
  .badge.new{background:#e6f4ea;color:#1e7a3d}
  .badge.update{background:#fff4e0;color:#9a6400}
  .src{margin:9px 0 0;font-size:12.5px;color:#777}
  .src a{color:#6b46c1;text-decoration:none}
  .watch{background:#fff;border:1px dashed #cfcdd6;border-radius:10px;padding:8px 16px;margin:10px 0}
  .watch .wi{padding:9px 0;border-bottom:1px solid #f0eef6;font-size:14px}
  .watch .wi:last-child{border-bottom:none}
  .watch a{color:#1a1a1a;font-weight:600;text-decoration:none}
  .watch .wn{color:#666;font-size:13px}
  .foot{color:#999;font-size:12px;text-align:center;margin:26px 0 6px}
"""


def _e(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _sources_html(srcs: list) -> str:
    if not srcs:
        return ""
    links = []
    for i, s in enumerate(srcs, 1):
        name = _e(s.get("name") or s.get("source") or f"source {i}")
        url = _e(s.get("url", ""))
        links.append(f'<a href="{url}">[{i}] {name}</a>' if url else f"[{i}] {name}")
    return '<div class="src">Sources: ' + " &nbsp;·&nbsp; ".join(links) + "</div>"


def _entry_html(entry: dict) -> str:
    status = (entry.get("status") or "").lower()
    badge = ""
    if status == "new":
        badge = '<span class="badge new">NEW</span>'
    elif status == "update":
        badge = '<span class="badge update">UPDATE</span>'
    why = _e(entry.get("why_it_matters", ""))
    detail = _e(entry.get("detail", ""))
    return (
        '<div class="card">'
        f'<h2>{badge}{_e(entry.get("headline", ""))}</h2>'
        + (f'<div class="why">{why}</div>' if why else "")
        + (f'<p class="detail">{detail}</p>' if detail else "")
        + _sources_html(entry.get("sources", []))
        + "</div>"
    )


def _watch_html(watch: list) -> str:
    if not watch:
        return ""
    rows = []
    for w in watch:
        url, title = _e(w.get("url", "")), _e(w.get("title", ""))
        chan, note = _e(w.get("channel", "")), _e(w.get("note", ""))
        link = f'<a href="{url}">{title}</a>' if url else title
        rows.append(
            f'<div class="wi">{link} &nbsp;<span class="wn">— {chan}</span>'
            + (f'<br><span class="wn">{note}</span>' if note else "")
            + "</div>"
        )
    return (
        f'<div class="beat">{_e(BEAT_LABEL["watch"])}</div>'
        '<div class="watch">' + "".join(rows) + "</div>"
    )


def render_briefing(data: dict) -> tuple[str, str]:
    """Pure: crafted briefing dict -> (html_document, subject). Unit-testable."""
    date = data.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by_beat = {s.get("beat"): s.get("entries", []) for s in data.get("sections", [])}

    body_parts: list[str] = []
    counts: list[str] = []
    for beat in BEAT_ORDER:
        entries = by_beat.get(beat, [])
        if not entries:
            continue
        counts.append(f"{len(entries)} {beat}")
        body_parts.append(f'<div class="beat">{_e(BEAT_LABEL.get(beat, beat))}</div>')
        body_parts.extend(_entry_html(e) for e in entries)

    watch = data.get("watchlist", [])
    if watch:
        body_parts.append(_watch_html(watch))

    if not body_parts:
        body_parts.append('<div class="card"><p class="detail">Nothing material since '
                          "your last briefing. Enjoy the quiet. 🌙</p></div>")

    intro = _e(data.get("intro", ""))
    html_doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<style>{_STYLE}</style></head><body><div class='wrap'>"
        f"<div class='head'><h1>Your briefing · {_e(date)}</h1>"
        + (f"<div class='intro'>{intro}</div>" if intro else "")
        + "</div>"
        + "".join(body_parts)
        + "<div class='foot'>Synthesized from your sources · every claim is cited · "
        "only what changed since last time.</div>"
        "</div></body></html>"
    )
    summary = " · ".join(counts) if counts else "quiet night"
    subject = f"Your briefing · {date} · {summary}"
    return html_doc, subject


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3: render the crafted briefing to HTML.")
    parser.add_argument("--in", dest="inp", default="briefing/output.json", help="Crafted briefing JSON.")
    parser.add_argument("--out", default="briefing.html", help="Output HTML path.")
    args = parser.parse_args()

    try:
        data = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[render] ERROR: could not read {args.inp}: {e}", file=sys.stderr)
        sys.exit(1)

    html_doc, subject = render_briefing(data)
    Path(args.out).write_text(html_doc, encoding="utf-8")
    print(f"SUBJECT: {subject}")
    print(f"OUT: {args.out}")


if __name__ == "__main__":
    main()
