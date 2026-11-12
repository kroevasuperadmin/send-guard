"""Filesystem ledger with atomic per-recipient, per-campaign claims.

``mkdir`` either creates the directory or fails because it exists, in one
kernel step. That makes it a safe claim primitive across processes, shells and
cron jobs on the same machine (and on NFS, where ``O_EXCL`` file creation is
less trustworthy).
"""

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .keys import entry_name, normalise_recipient, validate_campaign

DEFAULT_DIR = ".send-guard"
ENV_DIR = "SEND_GUARD_LEDGER"


def default_ledger_dir() -> Path:
    return Path(os.environ.get(ENV_DIR) or DEFAULT_DIR)


@dataclass
class Claim:
    campaign: str
    recipient: str
    path: Path


class Ledger:
    def __init__(self, directory: Optional[os.PathLike] = None):
        self.dir = Path(directory) if directory else default_ledger_dir()

    def path_for(self, campaign: str, recipient: str) -> Path:
        return self.dir / entry_name(campaign, recipient)

    def claim(self, campaign: str, recipient: str) -> Optional[Claim]:
        """Atomically claim (campaign, recipient). Returns None if already claimed."""
        campaign = validate_campaign(campaign)
        recipient = normalise_recipient(recipient)
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.path_for(campaign, recipient)
        try:
            path.mkdir()
        except FileExistsError:
            return None
        meta = {
            "campaign": campaign,
            "recipient": recipient,
            "claimed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pid": os.getpid(),
            "host": socket.gethostname(),
        }
        (path / "claim.json").write_text(json.dumps(meta) + "\n", encoding="utf-8")
        return Claim(campaign, recipient, path)
