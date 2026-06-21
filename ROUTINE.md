# Nightly routine

This is the orchestration Claude follows each night. The heavy, deterministic
work lives in the Python scripts; Claude does the smart parts (summarising) and
the connector I/O (reading the last digest date from Gmail, sending the email).

> **Where this runs:** in your Claude environment that has the **Gmail / Google
> Workspace connector** attached (this is what reads the last-digest date and
> sends the email). The remote "Claude Code on the web" environment is for
> *developing* the scripts — it has no Gmail connector.

## Steps

1. **Setup (idempotent).** The execution environment is ephemeral, so install
   deps every run:
   ```bash
   bash setup.sh
   ```
   This installs `yt-dlp`, patches certifi for the TLS-intercepting proxy, and
   builds the PO-token provider (for reliable transcripts — see Reliability).

2. **Determine the dedup cutoff from Gmail.** Using the Gmail connector, find
   the most recent newsletter you sent yourself, e.g. search
   `from:me subject:"YouTube Digest"` (or your chosen label), and take its
   `Date`. If none exists (first run), use 24 hours ago. Format as ISO-8601,
   e.g. `2026-06-20T08:30:00Z`.

3. **Fetch new videos + content.**
   ```bash
   python3 fetch_videos.py \
     --channels config/channels.txt \
     --since "$CUTOFF" \
     --out /tmp/yt-newsletter/items.json
   ```
   Reads each channel's RSS feed (reliable, no auth), keeps videos published
   after `--since`, and attaches each video's description (from RSS) and
   transcript (best-effort via yt-dlp; see Reliability).

4. **Summarise.** Read `/tmp/yt-newsletter/items.json`. For each item, write a
   2–4 sentence `summary` using the transcript when present, otherwise the
   description. Write the `summary` field back into each item in the JSON.
   (Optionally also write a one-line digest intro.)

5. **Build the HTML digest.**
   ```bash
   python3 build_digest.py /tmp/yt-newsletter/items.json \
     --out /tmp/yt-newsletter/digest.html --title "YouTube Digest"
   ```

6. **Email it.** Using the Gmail connector, send `/tmp/yt-newsletter/digest.html`
   as an **HTML email** to yourself, subject `YouTube Digest — <date>`. Keep the
   subject prefix stable so step 2 can find it next time. If there were no new
   videos, skip sending (or send a short "nothing new" note — your choice).

## Dedup model

Stateless. The "what's already been sent" boundary is the timestamp of the last
digest email in Gmail. Nothing is stored on disk or in the repo. This is robust
to the ephemeral environment and needs no database.

## Reliability — transcripts (IMPORTANT)

The core digest (title, channel, description, thumbnail, publish date, views)
comes from the **RSS feed** and is reliable from any IP.

**Transcripts** are the exception. yt-dlp must pass YouTube's "sign in to
confirm you're not a bot" check, which on datacenter/cloud IPs requires a
**PO token**. `setup.sh` builds the bgutil PO-token provider, but token
generation also needs **egress to `www.google.com`** (it loads YouTube's
BotGuard interpreter VM from `//www.google.com/js/th/…js`).

So for reliable transcripts you need **one** of:

- **(A) Egress:** allow `www.google.com` (and `www.gstatic.com`) in the
  environment's network policy, or set it to **Full**. Then the PO-token
  provider works and the `web` client succeeds. No account, no maintenance.
- **(B) Cookies:** export your YouTube cookies to `config/cookies.txt`
  (Netscape format) and set `YT_DLP_EXTRA_ARGS="--cookies config/cookies.txt"`.
  Works without the egress change, but carries some account risk and cookies
  expire.

Without either, transcript extraction is best-effort (often blocked on cloud
IPs) and summaries fall back to the description — the digest still builds and
sends, just with thinner per-video summaries for channels that write sparse
descriptions.

## Tier 2 (later)

Keyframe extraction + vision. Needs the **video file** to download, which is
gated by the same bot check as transcripts (so it needs option A or B above),
plus `ffmpeg` for frame extraction. Not built yet.
