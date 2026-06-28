#!/usr/bin/env python3
"""Send the rendered digest as an HTML email over SMTP.

Provider-agnostic: host, port, credentials, and recipient ALL come from the
environment (GitHub Actions secrets) — nothing is hardcoded, so the same script
works for Gmail, Zoho, Fastmail, etc. without code changes.

Security: the recipient(s) are fixed by the RECIPIENT_EMAIL secret and are
NEVER taken from the email body, the subject, or any model output — so a
prompt-injected transcript cannot redirect where the mail goes. This script
holds the only send capability in the pipeline; the model never sees these
secrets.

Environment:
  SMTP_HOST       e.g. smtp.gmail.com / smtp.zoho.com / smtp.zoho.in
  SMTP_PORT       465 for implicit SSL, or 587 for STARTTLS (default: 465)
  SMTP_USERNAME   the authenticating account; also used as the From address
  SMTP_PASSWORD   app-specific password (not your normal login password)
  RECIPIENT_EMAIL where to deliver; one address, or several comma-separated
                  (e.g. "me@example.com, friend@example.com")
  EMAIL_SUBJECT   optional; overridden by an argv[2] subject if given

Usage:
  python scripts/send_email.py <path-to-html> [subject]
"""

from __future__ import annotations

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(f"[send] ERROR: missing required env var {name}")
    return val


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: send_email.py <html-file> [subject]")
    html_path = sys.argv[1]
    with open(html_path, encoding="utf-8") as f:
        html_body = f.read()

    host = _require("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "465"))
    username = _require("SMTP_USERNAME")
    password = _require("SMTP_PASSWORD")
    # One or more addresses, comma-separated in the single RECIPIENT_EMAIL
    # secret (e.g. "me@x.com, friend@y.com"). Split + trim into a clean list.
    recipients = [r.strip() for r in _require("RECIPIENT_EMAIL").split(",") if r.strip()]
    if not recipients:
        sys.exit("[send] ERROR: RECIPIENT_EMAIL has no valid addresses")
    subject = (
        (sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].strip() else "")
        or os.environ.get("EMAIL_SUBJECT", "").strip()
        or "YouTube study notes"
    )

    msg = EmailMessage()
    msg["From"] = username
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content("This digest is HTML; open it in an HTML-capable mail client.")
    msg.add_alternative(html_body, subtype="html")

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx) as server:
            server.login(username, password)
            server.send_message(msg, to_addrs=recipients)
    else:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(username, password)
            server.send_message(msg, to_addrs=recipients)

    print(f"[send] sent '{subject}' to {', '.join(recipients)} via {host}:{port}")


if __name__ == "__main__":
    main()
