"""Ready-made look-back hook: is the recipient already in my IMAP Sent folder?

Use it as the check command:

    export IMAP_HOST=imap.example.com IMAP_USER=me@example.com IMAP_PASSWORD=...
    send-guard claim launch ada@example.com --check-cmd "python -m send_guard.imap_check"

Environment: IMAP_HOST, IMAP_USER, IMAP_PASSWORD (required); IMAP_PORT (993);
IMAP_SENT_FOLDER (Sent). The guard passes SEND_GUARD_RECIPIENT and SEND_GUARD_DAYS.
Exit 0 means not found, 10 means found, anything else means the check failed.
"""

import imaplib
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

FOUND = 10
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def imap_date(moment: datetime) -> str:
    """IMAP SINCE wants DD-Mon-YYYY in English whatever the locale."""
    return f"{moment.day:02d}-{_MONTHS[moment.month - 1]}-{moment.year}"


def count_sent(
    recipient: str,
    days: float,
    host: str,
    user: str,
    password: str,
    port: int = 993,
    folder: str = "Sent",
    connect: Callable[..., "imaplib.IMAP4"] = imaplib.IMAP4_SSL,
    now: Optional[datetime] = None,
) -> int:
    """Number of messages in ``folder`` addressed to ``recipient`` in the last ``days`` days."""
    since = imap_date((now or datetime.now(timezone.utc)) - timedelta(days=days))
    conn = connect(host, port)
    try:
        conn.login(user, password)
        status, _ = conn.select(f'"{folder}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"cannot open folder {folder!r}")
        # IMAP strings are quoted; recipient was validated upstream and has no quotes or spaces.
        status, data = conn.search(None, "SINCE", since, "TO", f'"{recipient}"')
        if status != "OK":
            raise RuntimeError("IMAP search failed")
        return len(data[0].split()) if data and data[0] else 0
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def main() -> int:
    try:
        recipient = os.environ["SEND_GUARD_RECIPIENT"]
        days = float(os.environ.get("SEND_GUARD_DAYS", "7"))
        host, user, password = (os.environ[k] for k in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD"))
        n = count_sent(
            recipient, days, host, user, password,
            port=int(os.environ.get("IMAP_PORT", "993")),
            folder=os.environ.get("IMAP_SENT_FOLDER", "Sent"),
        )
    except KeyError as exc:
        print(f"missing environment variable {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"imap check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if n:
        print(f"{n} message(s) to {recipient} in Sent within {days:g}d")
        return FOUND
    print(f"0 messages to {recipient} in Sent within {days:g}d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
