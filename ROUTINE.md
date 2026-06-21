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

**Transcripts** are the exception: yt-dlp must pass YouTube's "sign in to
confirm you're not a bot" check, which fails on datacenter/cloud IPs. **This
project authenticates with cookies** to get past it.

### Cookies setup (chosen path)

1. Export your YouTube cookies in **Netscape format** (e.g. the "Get cookies.txt"
   browser extension, while signed in to YouTube). Use a throwaway/secondary
   Google account if you're cautious — automated access from a cloud IP can get
   an account flagged.
2. Make them available to the run, either:
   - place the file at **`config/cookies.txt`** (gitignored — never committed), or
   - inject at runtime via **`$YT_COOKIES_FILE`** (point it at a path you write
     from a stored secret), or pass **`--cookies <path>`** to `fetch_videos.py`.
3. `fetch_videos.py` auto-detects `config/cookies.txt` / `$YT_COOKIES_FILE`. It
   logs `using cookies: …` when active.

Cookies expire — if transcripts start failing with "sign in to confirm…",
refresh `cookies.txt`. Without cookies, transcript extraction is best-effort
(usually blocked on cloud IPs) and summaries fall back to the description; the
digest still builds and sends.

> Alternative (not used here): a PO-token provider (`BUILD_POT=1` in `setup.sh`)
> plus `www.google.com` egress. Avoids cookies/account risk but needs the egress
> change. See `setup.sh`.

## Tier 2 (later)

Keyframe extraction + vision. Needs the **video file** to download, which is
gated by the same bot check — so it uses the same `cookies.txt` — plus `ffmpeg`
for frame extraction. Not built yet.
