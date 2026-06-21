# yt-newsletter

A nightly routine, run inside Claude Code, that fetches recent videos from your
YouTube subscriptions, summarises them, dedupes against what you've already
seen, builds an HTML digest, and emails it to you via the Gmail connector.

**Pure routine, no stored state.** Artifacts (transcripts, HTML, frames) are
ephemeral (`/tmp`, never committed). Dedup is derived from Gmail — each run only
includes videos published after your last digest email.

## Layout

| File | Purpose |
|------|---------|
| `fetch_videos.py` | RSS → new videos since cutoff → description + transcript → `items.json` |
| `build_digest.py` | `items.json` (+ Claude summaries) → `digest.html` |
| `setup.sh` | install deps, fix certifi, build the PO-token provider |
| `config/channels.example.txt` | template for your subscribed channels |
| `ROUTINE.md` | the nightly orchestration Claude follows (incl. Gmail steps) |
| `probe_v2.sh` | environment/egress diagnostic |

## Quick start

```bash
bash setup.sh
cp config/channels.example.txt config/channels.txt   # then add your channels
python3 fetch_videos.py --since 2026-06-20T00:00:00Z --out /tmp/yt-newsletter/items.json
python3 build_digest.py /tmp/yt-newsletter/items.json --out /tmp/yt-newsletter/digest.html
```

See **[ROUTINE.md](ROUTINE.md)** for the full nightly flow (cutoff from Gmail →
fetch → summarise → build → send).

## How it works

- **Input / dedup:** each channel's public **RSS feed** gives the latest ~15
  videos with publish times, description, thumbnail and view count — no auth,
  not bot-gated, reliable from any IP. Videos published after the cutoff
  (timestamp of your last digest, from Gmail) are kept.
- **Content:** descriptions come from RSS; **transcripts** come from yt-dlp
  subtitles (best-effort — see below).
- **Summarise + send:** Claude summarises each video and the Gmail connector
  sends the HTML digest — both run in your connector-enabled Claude environment.

## Reliability note (transcripts)

The core digest is reliable everywhere. **Transcripts** (and, later, Tier 2
video downloads) must pass YouTube's bot check, which fails on cloud IPs. This
project gets past it with **cookies**: put a Netscape `cookies.txt` at
`config/cookies.txt` (or set `$YT_COOKIES_FILE`). Without cookies, transcripts
are best-effort and summaries fall back to the description. Full setup in
[ROUTINE.md](ROUTINE.md#cookies-setup-chosen-path).

## Status

- **Tier 1** (transcript + description → dedup → HTML → email): built.
- **Tier 2** (keyframe extraction + vision): not yet.
