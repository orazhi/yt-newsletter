# yt-newsletter

A nightly routine, run inside Claude, that turns your YouTube subscriptions into
**deep study notes you can read instead of watching**. For each recent upload it
fetches the transcript and has Claude write near-complete notes — the actual
ideas, arguments, examples, numbers, and takeaways, section by section with
timestamps — then emails you the digest via the Gmail connector.

The goal is simple: get the knowledge and wisdom of an hour-long video in a
few minutes of reading, and only open YouTube when you actually want to watch.

**Cookie-free.** Channel listing uses each channel's public **RSS feed** and
content comes from the **transcript API** — both unauthenticated and not
bot-gated. The only secret is `ANTHROPIC_API_KEY` for the summaries.

**Pure routine, no stored state.** Artifacts (HTML, transcripts) are ephemeral
(`/tmp`, never committed). Dedup is derived from Gmail — each run only includes
videos published after your last digest email.

## Layout

| Path | Purpose |
|------|---------|
| `yt_newsletter/sources.py` | channel handle/URL → recent uploads via RSS (no auth) |
| `yt_newsletter/transcript.py` | timestamped transcript via youtube-transcript-api |
| `yt_newsletter/summarize.py` | transcript → deep study notes (Claude, structured output) |
| `yt_newsletter/render.py` | study notes → email-friendly HTML (unit-tested) |
| `yt_newsletter/pipeline.py` · `__main__.py` | orchestration + `python -m` CLI |
| `config/channels.example.txt` | template for your subscribed channels |
| `tests/` | offline tests for the renderer and RSS parser |
| `setup.sh` | install deps (idempotent) |
| `ROUTINE.md` | the nightly orchestration Claude follows (incl. Gmail steps) |

## Quick start

```bash
bash setup.sh
cp config/channels.example.txt config/channels.txt   # then add your channels
export ANTHROPIC_API_KEY=...                          # for the deep summaries
python -m yt_newsletter --since 2026-06-20T00:00:00Z --out /tmp/yt-newsletter/digest.html
```

It prints `SUBJECT:` and `OUT:` lines; open the HTML to eyeball it. See
**[ROUTINE.md](ROUTINE.md)** for the full nightly flow (cutoff from Gmail →
build → send).

## How it works

1. **List recent uploads (no auth).** Each channel's public RSS feed
   (`/feeds/videos.xml?channel_id=…`) lists recent videos with id, title,
   publish time, description, and thumbnail. Handles/custom URLs are resolved to
   a channel id automatically. Videos published after `--since` are kept.
2. **Get the transcript (no cookies).** `youtube-transcript-api` pulls the
   caption track YouTube already serves — this sidesteps the bot-wall that blocks
   yt-dlp's extraction/download path. Timestamps are preserved.
3. **Write deep study notes.** Claude (`claude-opus-4-8`, structured outputs +
   adaptive thinking) turns the transcript into a faithful, section-by-section
   knowledge transfer: TL;DR, the actual arguments/examples/numbers, insights,
   takeaways, glossary, and references.
4. **Render + send.** The renderer builds the HTML digest; the Gmail connector
   (in your connector-enabled Claude environment) emails it to you.

## Configuration

All optional, via env vars:

| Var | Default | Meaning |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | — | **required** for summaries |
| `YT_NEWSLETTER_CHANNELS` | — | comma-separated channels (overrides `config/channels.txt`) |
| `YT_NEWSLETTER_MODEL` | `claude-opus-4-8` | summarization model (`claude-haiku-4-5` for cheaper) |
| `YT_NEWSLETTER_EFFORT` | `high` | thinking effort: `low`/`medium`/`high`/`xhigh`/`max` |
| `YT_NEWSLETTER_MAX_PER_CHANNEL` | `5` | cap videos per channel per run |
| `YT_NEWSLETTER_MAX_SUMMARY_TOKENS` | `16000` | output cap (raise for very long videos) |
| `YT_NEWSLETTER_MAX_TRANSCRIPT_CHARS` | `120000` | transcript chars fed to the model |

## Reliability notes

- RSS + transcript are unauthenticated and work from any IP. On a heavily
  flagged datacenter IP the feed endpoint can throttle intermittently
  (occasional 404/500); `sources._http_get` retries with backoff to ride
  through it. A video with no captions (live, music-only, subs disabled) falls
  back to title/description and is flagged in the digest.
- Transcripts can rarely be rate-limited; the run skips to description-only for
  that video rather than failing the whole digest.

## Status

- **Tier 1** (transcript → deep study notes → HTML → email): **built & tested.**
- **Tier 2** (keyframe extraction + vision for slides/animation-heavy videos):
  not yet — see [PLAN.md](PLAN.md).
