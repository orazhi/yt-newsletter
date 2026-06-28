# yt-newsletter

A **nightly personal intelligence briefing** — "a diff of the world since last
night" — researched, deduplicated, and cited, in your inbox by morning.

Instead of you watching a stack of YouTube channels, a GitHub Actions cron pulls
the *same* wisdom from each creator's most **accessible** source — newsletters
(The Batch, TLDR sec, Data Elixir), the arXiv API, Hacker News, blogs, and for
the video-only channels the YouTube RSS *listing* — then removes anything you
were already briefed on, clusters the same story across sources, and has Claude
write a tight, sectioned briefing where **every claim traces to a source URL**.
It runs unattended in the cloud, so it works while your laptop is off.

Three beats — **AI & Engineering**, **News & Current Affairs**, **Money &
Life** — plus a **watchlist** at the bottom: the recent videos from your
channels whose topic the text sections *didn't* already cover (so you only open
YouTube for what's genuinely additive).

## Why it isn't IP-blocked

YouTube's transcript API bot-walls datacenter IPs, which is why scraping it from
a cloud runner fails. RSS, the arXiv API, Hacker News, and the YouTube RSS
*listing* (titles + descriptions only) are **not** walled that way — so the
briefing fetches happily from a GitHub Actions runner with your laptop in a
cupboard.

## How it works — four stages, one ephemeral runner

| # | Stage | Module | Secrets |
|---|-------|--------|---------|
| 1 | **gather** — fetch every source, drop anything seen before, cluster dups | `gather.py` → `feeds.py`, `briefing.py` | none |
| 2 | **synth** — Claude reads `input.json`, writes the crafted briefing JSON | `claude-code-action` | OAuth token |
| 3 | **render** — briefing JSON → HTML email | `render_brief.py` | none |
| 4 | **email** — SMTP-send it, then fold tonight's items into memory | `send_email.py`, `briefing.py` | SMTP |

**The diff ("since last night").** A small `state/memory.json` maps each story's
canonical key → the date it was first sent. It lives in the **Actions cache**
(not committed to the repo), is restored at the start of each run and saved at
the end, and self-prunes at 45 days. Items already in memory are filtered out
before Claude ever sees them; a story is only folded into memory *after* a
successful send, so a failed run never silently "uses up" news.

**Injection-hardening.** Stage 1 fetches feeds but holds no secrets. Stage 2
runs Claude with **offline tools only** (`Read`/`Write`/`Glob`; no
`Bash`/`WebFetch`/`WebSearch`), so untrusted feed text can neither run commands
nor invent citations — every URL in the output must come from the fetched input.

## Layout

| Path | Purpose |
|------|---------|
| `yt_newsletter/feeds.py` | the source registry: every feed + which beat it serves |
| `yt_newsletter/gather.py` | Stage 1 — fetch all sources, normalize into Items (stdlib RSS/Atom/HN parsers) |
| `yt_newsletter/briefing.py` | dedup, clustering, and the cross-night memory/diff (unit-tested) |
| `yt_newsletter/render_brief.py` | synthesized briefing JSON → HTML email (unit-tested) |
| `yt_newsletter/sources.py` | YouTube RSS listing + a retrying HTTP helper (reused by gather) |
| `yt_newsletter/models.py` | shared data structures (`Video`) |
| `scripts/send_email.py` | provider-agnostic SMTP sender |
| `.github/workflows/briefing.yml` | the nightly cron that runs all four stages |
| `tests/` | offline tests for the briefing engine and the RSS parser |

## Setup

The whole pipeline is **stdlib-only** (no `pip install`), so there's nothing to
build. You only configure secrets, under
**Settings → Secrets and variables → Actions → Secrets**:

| Secret | Used by | How to get it |
|--------|---------|---------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Stage 2 | run `claude setup-token` (Pro/Max subscription) |
| `SMTP_HOST` / `SMTP_PORT` | Stage 4 | your mail provider |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Stage 4 | mailbox / app password |
| `RECIPIENT_EMAIL` | Stage 4 | where the briefing is delivered (never set from model output) |

No repository **variables** are needed — the source list lives in `feeds.py`.

## Running it

It runs automatically every night (`cron: "30 1 * * *"` ≈ 07:00 IST). To run it
on demand: **Actions → Nightly briefing → Run workflow** (optionally set the
lookback, e.g. `3d` or `36h`).

To edit *what* it follows, edit the `_AI` / `_NEWS` / `_MONEY` / `_WATCH` lists
in `yt_newsletter/feeds.py`.

## Tests

```bash
python tests/test_briefing.py    # dedup / clustering / memory / parsers / render
python tests/test_sources.py     # YouTube RSS listing parser
```

Both are offline (no network, no model).
