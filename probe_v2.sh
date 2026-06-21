#!/usr/bin/env bash
#
# probe_v2.sh — environment/egress diagnostic for the yt-newsletter routine.
#
# Confirms the things the nightly routine depends on, in this (datacenter)
# execution environment:
#   1. egress to YouTube + PyPI
#   2. the certifi/TLS-interception fix (the egress proxy MITMs TLS with a
#      self-signed CA that is in the SYSTEM bundle but NOT in certifi's bundle,
#      which is what yt-dlp uses)
#   3. video metadata + description extraction        (Tier 1 content)
#   4. subtitle/transcript extraction via yt-dlp      (Tier 1 content)
#   5. video media download                           (Tier 2 keyframes)
#
# Findings (2026-06): metadata + subtitles work; raw media download and the
# youtube_transcript_api library are gated by "Sign in to confirm you're not a
# bot" / "RequestBlocked" because the proxy egress IP is a datacenter IP. The
# yt-dlp subtitle path succeeds for most videos but is probabilistic. See
# README for the reliability options (PO-token provider / cookies).
#
# Usage:  bash probe_v2.sh [VIDEO_ID ...]
set -uo pipefail

CA="/etc/ssl/certs/ca-certificates.crt"
WORK="${TMPDIR:-/tmp}/yt-probe"
VIDS=("$@")
if [ ${#VIDS[@]} -eq 0 ]; then
  # default mix: manual-subs, auto-captions(long), auto-captions(music)
  VIDS=(jNQXAC9IVRw aircAruvnKk dQw4w9WgXcQ)
fi

pass=0; fail=0
ok()   { echo "  [PASS] $*"; pass=$((pass+1)); }
bad()  { echo "  [FAIL] $*"; fail=$((fail+1)); }
hr()   { echo "------------------------------------------------------------"; }

echo "yt-newsletter probe v2 — $(date -u +%FT%TZ)"
hr

# --- 0. tooling -------------------------------------------------------------
echo "[0] tooling"
command -v yt-dlp  >/dev/null && ok "yt-dlp $(yt-dlp --version 2>/dev/null)" || bad "yt-dlp missing (pip install yt-dlp)"
command -v python3 >/dev/null && ok "python3 $(python3 -c 'import sys;print(sys.version.split()[0])')" || bad "python3 missing"

# --- 1. TLS-interception / certifi fix -------------------------------------
# yt-dlp validates against certifi's bundle and ignores SSL_CERT_FILE; the
# proxy CA lives only in the system bundle, so make certifi's bundle = system.
echo "[1] certifi / TLS-interception fix"
if [ -f "$CA" ]; then
  CERTIFI="$(python3 -c 'import certifi;print(certifi.where())' 2>/dev/null)"
  if [ -n "$CERTIFI" ] && ! cmp -s "$CA" "$CERTIFI"; then
    cp "$CA" "$CERTIFI" && ok "patched certifi bundle -> system bundle ($(grep -c 'BEGIN CERTIFICATE' "$CERTIFI") certs)"
  else
    ok "certifi already matches system bundle"
  fi
else
  bad "system CA bundle not found at $CA"
fi

# --- 2. egress --------------------------------------------------------------
echo "[2] egress"
for url in https://www.youtube.com/ https://youtubei.googleapis.com/ https://pypi.org/simple/; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$url" 2>/dev/null)
  # any non-000 response means we reached the host (405/404 are fine)
  [ -n "$code" ] && [ "$code" != "000" ] && ok "$url -> $code" || bad "$url unreachable"
done

# --- 3/4/5. per-video extraction -------------------------------------------
rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK" || exit 1
for vid in "${VIDS[@]}"; do
  hr; echo "video $vid"
  url="https://www.youtube.com/watch?v=$vid"

  # [3] metadata + description
  meta=$(yt-dlp --no-warnings --skip-download \
    --print "%(title)s\t%(channel)s\t%(upload_date)s\t%(duration)s" "$url" 2>/dev/null)
  if [ -n "$meta" ]; then
    IFS=$'\t' read -r title channel udate dur <<<"$meta"
    ok "metadata: ${title} | ${channel} | ${udate} | ${dur}s"
  else
    bad "metadata extraction failed"
  fi

  # [4] subtitles / transcript (Tier 1 content path)
  rm -f "$vid".*.vtt 2>/dev/null
  suberr=$(yt-dlp --no-warnings --skip-download --write-subs --write-auto-subs \
    --sub-langs "en.*" --sub-format vtt -o "%(id)s.%(ext)s" "$url" 2>&1)
  f=$(ls "$vid".*.vtt 2>/dev/null | head -1)
  if [ -n "$f" ]; then
    words=$(grep -vE '^([0-9]{2}:|WEBVTT|Kind:|Language:|NOTE|$)' "$f" | sed 's/<[^>]*>//g' | wc -w)
    ok "subtitles: $f (~${words} words)"
  else
    reason=$(echo "$suberr" | grep -iE 'sign in|blocked|no subtitle|unavailable' | head -1 | sed 's/^[[:space:]]*//')
    bad "subtitles: ${reason:-none}"
  fi

  # [5] media download (Tier 2) — best effort, expected to fail on datacenter IP
  rm -f "$vid".f* "$vid".mp4 "$vid".webm 2>/dev/null
  dlerr=$(yt-dlp --no-warnings -f "worst" --max-filesize 50M \
    -o "%(id)s.%(ext)s" "$url" 2>&1)
  if ls "$vid".mp4 "$vid".webm >/dev/null 2>&1; then
    ok "media download ok"
  else
    reason=$(echo "$dlerr" | grep -iE 'sign in|forbidden|drm|blocked' | head -1 | sed 's/^[[:space:]]*//')
    echo "  [WARN] media download failed (Tier 2 only): ${reason:-unknown}"
  fi
done

hr
echo "SUMMARY: ${pass} pass, ${fail} fail"
echo "work dir: $WORK (ephemeral — not committed)"
[ "$fail" -eq 0 ] && exit 0 || exit 1
