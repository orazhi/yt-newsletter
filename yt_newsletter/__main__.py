"""CLI entry point: python -m yt_newsletter --since <iso> --out <path>.

The nightly routine derives `--since` from the last digest it emailed, runs this
module to write the HTML, then sends that file via the Gmail connector.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from .pipeline import run


def _default_since() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deep YouTube study-notes digest.")
    parser.add_argument(
        "--since",
        default=_default_since(),
        help="ISO-8601 cutoff; only videos published after this are included "
        "(default: last 24h). The routine derives this from the last email sent.",
    )
    parser.add_argument(
        "--out",
        default="/tmp/yt-newsletter/digest.html",
        help="Where to write the digest HTML (default: /tmp/yt-newsletter/digest.html).",
    )
    args = parser.parse_args()

    import os

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    out_path, subject = run(args.since, args.out)
    # Printed so the nightly routine agent can pick them up and send via Gmail.
    print(f"SUBJECT: {subject}")
    print(f"OUT: {out_path}")


if __name__ == "__main__":
    main()
