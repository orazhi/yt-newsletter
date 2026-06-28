#!/usr/bin/env bash
#
# setup.sh — prepare the environment for the yt-newsletter routine.
#
# Idempotent. Safe to re-run at the start of every nightly run (the execution
# environment is ephemeral, so dependencies are (re)installed each time).
#
#   1. install Python deps (youtube-transcript-api + anthropic, latest)
#   2. patch certifi -> system CA bundle (helps in TLS-intercepting proxy envs)
#
# No cookies, no yt-dlp, no PO-token provider: channel listing uses the public
# RSS feed and transcripts use youtube-transcript-api — both unauthenticated and
# not bot-gated. The only secret needed is ANTHROPIC_API_KEY (for the summaries).
set -uo pipefail
cd "$(dirname "$0")"

PIP="pip3 install --quiet --break-system-packages"
SYSTEM_CA="/etc/ssl/certs/ca-certificates.crt"

echo "[setup] installing python deps (latest anthropic for structured outputs)…"
$PIP -U -r requirements.txt 2>&1 | grep -viE "WARNING: Running pip" || true

echo "[setup] patching certifi -> system CA bundle (for proxied envs)…"
if [ -f "$SYSTEM_CA" ]; then
  CERTIFI="$(python3 -c 'import certifi;print(certifi.where())' 2>/dev/null || true)"
  if [ -n "$CERTIFI" ] && ! cmp -s "$SYSTEM_CA" "$CERTIFI"; then
    cp "$SYSTEM_CA" "$CERTIFI" && echo "[setup]   certifi updated to system CA bundle"
  else
    echo "[setup]   certifi already matches — skipping"
  fi
else
  echo "[setup]   no system CA bundle at $SYSTEM_CA (not a proxied env) — skipping"
fi

cat <<'NOTE'

[setup] done.

  Next:
    1. cp config/channels.example.txt config/channels.txt     # add your channels
    2. export ANTHROPIC_API_KEY=...                            # for deep summaries
    3. python -m yt_newsletter --since <ISO-8601> --out /tmp/yt-newsletter/digest.html

  Quick sanity check (offline, no API key needed):
    python tests/test_render.py && python tests/test_sources.py

  See ROUTINE.md for the full nightly flow (cutoff from Gmail -> build -> email).
NOTE
