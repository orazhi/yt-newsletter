"""Render StudyNotes into an email-friendly HTML digest.

Pure functions, no network — this is the unit-tested core. Styles are inlined
because most email clients strip <style> blocks. The layout is built for
reading/skimming: a TL;DR up top, then collapsible-feeling sections with the
actual content, insights, takeaways, glossary, and references.
"""

from __future__ import annotations

import html

from .models import StudyNotes

_WRAP = (
    "max-width:720px;margin:0 auto;padding:24px;"
    "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
    "color:#1a1a1a;line-height:1.55;"
)
_CARD = "padding:22px 0;border-bottom:2px solid #ececec;"
_TITLE = "margin:0 0 2px;font-size:20px;line-height:1.3;"
_LINK = "color:#0b5fff;text-decoration:none;"
_META = "margin:0 0 12px;font-size:13px;color:#666;"
_HOOK = "margin:0 0 12px;font-size:15px;font-style:italic;color:#444;"
_TLDR_BOX = (
    "margin:0 0 18px;padding:12px 14px;background:#f6f8ff;"
    "border-left:3px solid #0b5fff;border-radius:4px;font-size:15px;"
)
_H3 = "margin:18px 0 6px;font-size:16px;"
_SEC_HEAD = "margin:16px 0 4px;font-size:15px;font-weight:600;"
_TS = "color:#0b5fff;font-weight:600;font-size:13px;margin-right:6px;"
_PROSE = "margin:0 0 8px;font-size:14.5px;"
_UL = "margin:0 0 10px;padding-left:20px;font-size:14px;color:#333;"
_SMALL = "font-size:13px;color:#555;"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _ul(items: list[str], style: str = _UL) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(it)}</li>" for it in items if it)
    return f'<ul style="{style}">{lis}</ul>' if lis else ""


def render_subject(items: list[StudyNotes], date: str) -> str:
    n = len(items)
    if n == 0:
        return f"YouTube study notes — {date}: nothing new"
    lead = items[0].video.title
    extra = f" +{n - 1} more" if n > 1 else ""
    return f"YouTube study notes — {date}: {lead}{extra}"


def _render_section(sec) -> str:
    head_ts = f'<span style="{_TS}">{_esc(sec.timestamp)}</span>' if sec.timestamp else ""
    return (
        f'<div style="{_SEC_HEAD}">{head_ts}{_esc(sec.heading)}</div>'
        + (f'<p style="{_PROSE}">{_esc(sec.summary)}</p>' if sec.summary else "")
        + _ul(sec.key_points)
        + _ul(sec.details, _SMALL + "margin:0 0 10px;padding-left:20px;")
    )


def _render_glossary(items) -> str:
    if not items:
        return ""
    rows = "".join(
        f'<li><b>{_esc(g.term)}</b> — {_esc(g.definition)}</li>' for g in items if g.term
    )
    return f'<h3 style="{_H3}">Glossary</h3><ul style="{_UL}">{rows}</ul>' if rows else ""


def _render_item(item: StudyNotes) -> str:
    v = item.video
    parts = [f'<div style="{_CARD}">']
    parts.append(
        f'<h2 style="{_TITLE}"><a href="{_esc(v.url)}" style="{_LINK}">{_esc(v.title)}</a></h2>'
    )
    parts.append(f'<p style="{_META}">{_esc(v.channel)}</p>')
    if not item.transcript_found:
        parts.append(
            f'<p style="{_META}">⚠️ No transcript available — notes are based on '
            f"the title/description only.</p>"
        )
    if item.hook:
        parts.append(f'<p style="{_HOOK}">{_esc(item.hook)}</p>')
    if item.tldr:
        parts.append(f'<div style="{_TLDR_BOX}"><b>TL;DR</b> &middot; {_esc(item.tldr)}</div>')

    for sec in item.sections:
        parts.append(_render_section(sec))

    if item.insights:
        parts.append(f'<h3 style="{_H3}">Key insights</h3>')
        parts.append(_ul(item.insights))
    if item.takeaways:
        parts.append(f'<h3 style="{_H3}">Takeaways</h3>')
        parts.append(_ul(item.takeaways))
    parts.append(_render_glossary(item.glossary))
    if item.references:
        parts.append(f'<h3 style="{_H3}">References &amp; mentions</h3>')
        parts.append(_ul(item.references))

    parts.append(
        f'<p style="{_META}margin-top:12px;">'
        f'<a href="{_esc(v.url)}" style="{_LINK}">▶ Watch on YouTube</a></p>'
    )
    parts.append("</div>")
    return "".join(parts)


def render_digest(items: list[StudyNotes], date: str) -> str:
    """Return a complete HTML document for the given study notes."""
    header = (
        f'<h1 style="font-size:24px;margin:0 0 4px;">Your YouTube study notes</h1>'
        f'<p style="color:#666;font-size:13px;margin:0 0 18px;">{_esc(date)} '
        f"&middot; {len(items)} video(s) &middot; read instead of watch</p>"
    )
    if not items:
        body = '<p style="color:#666;">No new videos since the last digest.</p>'
    else:
        body = "".join(_render_item(it) for it in items)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'</head><body style="margin:0;background:#fff;"><div style="{_WRAP}">'
        f"{header}{body}</div></body></html>"
    )
