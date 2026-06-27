#!/usr/bin/env python3
"""Send the rendered digest as an HTML email over SMTP.

Provider-agnostic: host, port, credentials, and recipient ALL come from the
environment (GitHub Actions secrets) — nothing is hardcoded, so the same script
works for Gmail, Zoho, Fastmail, etc. without code changes.

Security: the recipient is fixed by the RECIPIENT_EMAIL secret and is NEVER
taken from the email body, the subject, or any model output — so a
prompt-injected transcript cannot redirect where the mail goes. This script
holds the only send capability in the pipeline; the model never sees these
secrets.

Environment:
  SMTP_HOST       e.g. smtp.gmail.com / smtp.zoho.com / smtp.zoho.in
  SMTP_PORT       465 for implicit SSL, or 587 for STARTTLS (default: 465)
  SMTP_USERNAME   the authenticating account; also used as the From address
  SMTP_PASSWORD   app-specific password (not your normal login password)
  RECIPIENT_EMAIL where to deliver (may be the same address as SMTP_USERNAME)
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
    recipient = _require("RECIPIENT_EMAIL")
    subject = (
        (sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].strip() else "")
        or os.environ.get("EMAIL_SUBJECT", "").strip()
        or "YouTube study notes"
    )

    msg = EmailMessage()
    msg["From"] = username
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content("This digest is HTML; open it in an HTML-capable mail client.")
    msg.add_alternative(html_body, subtype="html")

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx) as server:
            server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(username, password)
            server.send_message(msg)

    print(f"[send] sent '{subject}' to {recipient} via {host}:{port}")


if __name__ == "__main__":
    main()
