#!/usr/bin/env bash
#
# setup.sh — prepare the environment for the yt-newsletter routine.
#
# Idempotent. Safe to re-run at the start of every nightly run (the execution
# environment is ephemeral, so dependencies must be (re)installed each time).
#
#   1. install Python deps (yt-dlp + PO-token plugin)
#   2. patch certifi -> system CA bundle (TLS-interception fix; see probe_v2.sh)
#   3. (opt-in) build the bgutil PO-token provider for transcript auth
#
# Transcript auth: this project uses COOKIES (config/cookies.txt) to pass
# YouTube's bot check — no PO-token provider or www.google.com egress needed.
# The PO-token provider is an alternative; build it only if you set BUILD_POT=1.
set -uo pipefail
cd "$(dirname "$0")"

PIP="pip3 install --quiet --break-system-packages"
SYSTEM_CA="/etc/ssl/certs/ca-certificates.crt"
POT_DIR="${POT_DIR:-/root/bgutil-ytdlp-pot-provider}"

echo "[setup] installing python deps…"
$PIP -r requirements.txt 2>&1 | grep -viE "WARNING: Running pip" || true

echo "[setup] patching certifi -> system CA bundle…"
if [ -f "$SYSTEM_CA" ]; then
  CERTIFI="$(python3 -c 'import certifi;print(certifi.where())' 2>/dev/null || true)"
  if [ -n "$CERTIFI" ] && ! cmp -s "$SYSTEM_CA" "$CERTIFI"; then
    cp "$SYSTEM_CA" "$CERTIFI"
    echo "[setup]   certifi now has $(grep -c 'BEGIN CERTIFICATE' "$CERTIFI") certs"
  else
    echo "[setup]   certifi already matches (or no change needed)"
  fi
else
  echo "[setup]   no system CA bundle at $SYSTEM_CA (not a proxied env) — skipping"
fi

if [ -f config/cookies.txt ] && [ -s config/cookies.txt ]; then
  echo "[setup] config/cookies.txt present — transcripts will authenticate via cookies."
fi

if [ "${BUILD_POT:-0}" != "1" ]; then
  cat <<'NOTE'
[setup] done. (PO-token provider not built — chosen transcript path is cookies.)

  Put your YouTube cookies at  config/cookies.txt  (Netscape format), or inject
  them at runtime via $YT_COOKIES_FILE. Without cookies, transcripts are
  best-effort; the rest of the digest still works. To use the PO-token provider
  instead of cookies, re-run with BUILD_POT=1 (also needs www.google.com egress).
NOTE
  exit 0
fi

echo "[setup] BUILD_POT=1 — building bgutil PO-token provider (script mode)…"
SCRIPT="$POT_DIR/server/build/generate_once.js"
if [ -f "$SCRIPT" ]; then
  echo "[setup]   already built at $SCRIPT"
else
  if curl -sL --max-time 60 \
      https://codeload.github.com/Brainicism/bgutil-ytdlp-pot-provider/tar.gz/refs/heads/master \
      -o /tmp/bgutil.tar.gz 2>/dev/null; then
    rm -rf "$POT_DIR"
    mkdir -p "$(dirname "$POT_DIR")"
    tar xzf /tmp/bgutil.tar.gz -C "$(dirname "$POT_DIR")"
    mv "$(dirname "$POT_DIR")/bgutil-ytdlp-pot-provider-master" "$POT_DIR"
    ( cd "$POT_DIR/server" && npm install --no-audit --no-fund >/dev/null 2>&1 && npx tsc >/dev/null 2>&1 )
    if [ -f "$SCRIPT" ]; then
      echo "[setup]   built $SCRIPT"
    else
      echo "[setup]   WARN: build did not produce $SCRIPT — transcripts best-effort"
    fi
  else
    echo "[setup]   WARN: could not fetch provider source — transcripts best-effort"
  fi
fi

cat <<'NOTE'

[setup] done.

  Reliable transcripts also require egress to  www.google.com  (the BotGuard
  interpreter VM the PO-token provider loads). If www.google.com is blocked,
  the `web` player client cannot pass YouTube's bot check and transcripts fall
  back to best-effort. Add www.google.com (and www.gstatic.com) to the
  environment's egress allowlist, or set the network policy to Full.
NOTE
