# Nightly routine

This is the orchestration Claude follows each night. The heavy, deterministic
work lives in the `yt_newsletter` package; Claude does the connector I/O —
reading the last-digest date from Gmail and sending the email.

> **Where this runs:** in your Claude environment that has the **Gmail / Google
> Workspace connector** attached (that's what reads the last-digest date and
> sends the email). The remote "Claude Code on the web" environment is for
> *developing* the code — it has no Gmail connector.

## Steps

1. **Setup (idempotent).** The execution environment is ephemeral, so install
   deps every run:
   ```bash
   bash setup.sh
   ```
   Ensure `ANTHROPIC_API_KEY` is set and `config/channels.txt` exists (copy it
   from `config/channels.example.txt` once, then add your channels).

2. **Determine the dedup cutoff from Gmail.** Using the Gmail connector, find the
   most recent digest you sent yourself — search
   `from:me subject:"YouTube study notes"` — and take its `Date`. If none exists
   (first run), use 24 hours ago. Format as ISO-8601, e.g. `2026-06-20T08:30:00Z`.

3. **Build the digest.**
   ```bash
   python -m yt_newsletter --since "$CUTOFF" --out /tmp/yt-newsletter/digest.html
   ```
   This lists each channel's recent uploads (RSS), keeps those published after
   `--since`, fetches each transcript, has Claude write deep study notes, and
   writes the HTML. It prints two lines:
   ```
   SUBJECT: YouTube study notes — <date>: <lead title> +N more
   OUT: /tmp/yt-newsletter/digest.html
   ```

4. **Email it.** Using the Gmail connector, send the file at the `OUT:` path as
   an **HTML email** to yourself, using the printed `SUBJECT:`. Keep the subject
   prefix `YouTube study notes —` stable so step 2 can find it next time. If
   there were no new videos, the digest says so — skip sending, or send the
   short "nothing new" note, your choice.

## Dedup model

Stateless. The "what's already been sent" boundary is the timestamp of the last
digest email in Gmail. Nothing is stored on disk or in the repo — robust to the
ephemeral environment, no database needed.

## Reliability

- **Listing + transcripts are unauthenticated** (RSS feed + transcript API) and
  not bot-gated — no cookies, no yt-dlp. The feed fetch retries transient
  throttling (404/500) with backoff.
- **No transcript?** (live stream, music-only, subs disabled) — the notes fall
  back to the title/description for that one video and the digest flags it; the
  run continues.

## Cost control

Deep study notes use `claude-opus-4-8` at `effort=high` by default. For a
high-volume subscription list, set `YT_NEWSLETTER_MODEL=claude-haiku-4-5` and/or
`YT_NEWSLETTER_EFFORT=medium` to cut cost, and `YT_NEWSLETTER_MAX_PER_CHANNEL`
to bound how many videos per channel are summarized per run.

## Tier 2 (later)

Keyframe extraction + vision, for videos whose value is on-screen (slides,
animation, code) rather than spoken. Needs the **video file** (downloaded via
yt-dlp — that path *is* bot-gated, so it would use cookies) plus `ffmpeg` for
scene-change frame extraction, then a vision pass. Not built yet — see
[PLAN.md](PLAN.md).
