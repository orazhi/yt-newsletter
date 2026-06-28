# yt-newsletter — Plan & Architecture

Turn a set of YouTube channels into **deep study notes** emailed nightly, so you
can read/skim the knowledge of a video instead of watching it.

## Decisions (locked)

- **Cookie-free.** Channel listing uses the public RSS feed; transcripts use
  `youtube-transcript-api`. Both are unauthenticated and dodge the bot-wall that
  blocks yt-dlp's extraction/download path — so no cookies, no PO-token, no
  account-takeover-grade secrets in the repo. The only secret is
  `ANTHROPIC_API_KEY`.
- **Deep study notes, not blurbs.** The product is near-complete knowledge
  transfer: a faithful, section-by-section rendering of the video's actual
  content (arguments, examples, numbers, insights, takeaways, glossary,
  references), anchored to timestamps. A 2–3 sentence summary is explicitly *not*
  the goal — if all you wanted was the gist you'd just watch.
- **Plain Python package**, deterministic and testable. Claude is one
  structured-output API call inside the pipeline (`claude-opus-4-8`,
  `output_config.format`, adaptive thinking, streaming).
- **Pure routine, no committed state.** HTML/transcripts are ephemeral. Dedup is
  "published after the last digest email", read from Gmail — no database.
- **Email I/O is the routine agent's job**, not the module's. The module is a
  pure pipeline: take `--since`, fetch/transcribe/summarize, **write HTML to a
  file**, and print a subject. The nightly routine (Gmail-connector Claude) reads
  that file and sends the email.

## Data flow

```
config/channels.txt ─┐
                     ├─ sources.list_recent_videos(since)   [RSS, no auth] ─► [Video]
--since ─────────────┘                                                         │
                          transcript.get_segments(id)  [transcript API]  ─► [Segment] (timestamped)
                                                                               │
                          summarize.deep_study_notes(Claude)  ─► StudyNotes (sections, insights, …)
                                                                               │
                                 render.render_digest([StudyNotes])  ─► HTML file
                                                                               │
                          (routine agent) Gmail connector ─► email sent
```

## Modules

| File | Status |
|---|---|
| `models.py` | `Video`, `Section`, `GlossaryItem`, `StudyNotes` — stable |
| `render.py` + `tests/test_render.py` | **tested** (pure, no network) |
| `sources.py` + `tests/test_sources.py` | RSS resolve + parse **tested**; live-verified (retry/backoff for flagged-IP throttling) |
| `transcript.py` | live-verified (timestamped segments, 1.x + legacy API) |
| `summarize.py` | written to the claude-api skill spec; **needs a live API-key run** to verify the structured-output call end to end |
| `config.py`, `pipeline.py`, `__main__.py` | orchestration glue |

## Open verification (do in the connector environment, with a key)

1. `ANTHROPIC_API_KEY=… python -m yt_newsletter --since <date> --out /tmp/yt-newsletter/digest.html`
   on 1–2 real channels; eyeball the HTML depth.
2. Wire the routine: last-digest date from Gmail → run module → send the HTML via
   the Gmail connector. Confirm one real email lands.
3. Tune `effort` / model / max-tokens for your cost/depth preference.

## Why cookies aren't needed (and the leak we fixed)

Earlier exploration assumed transcripts needed cookies because *yt-dlp* hit
YouTube's "confirm you're not a bot" wall. But the RSS feed and the transcript
API are separate, unauthenticated endpoints that aren't bot-gated — verified
working even from a flagged datacenter IP. So cookies are moot for Tier 1.
(Bonus: `config/cookies.txt` and `config/channels.txt` were silently *not*
gitignored due to trailing inline comments on the pattern lines — fixed, since
real YouTube cookies are account-takeover-grade.)

## Tier 2 (later): keyframes + vision

Some videos carry their value on-screen (slides, animation, code) rather than in
speech. Plan: download the video (yt-dlp — this path *is* bot-gated, so it would
use cookies), extract scene-change keyframes with `ffmpeg`, run a vision pass,
and fold the visual notes into the same `StudyNotes`/HTML. Deferred until Tier 1
is confirmed in the live connector environment.
