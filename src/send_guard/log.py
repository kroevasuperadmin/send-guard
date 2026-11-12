"""Append-only JSON-lines audit log, one line per decision."""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_NAME = "guard.log"


def append(ledger_dir: Path, event: str, campaign: str, recipient: str, detail: str = "") -> None:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    line = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        "campaign": campaign,
        "recipient": recipient,
        "detail": detail,
    }
    # O_APPEND writes of one short line are atomic enough for concurrent guards.
    with open(ledger_dir / LOG_NAME, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")
