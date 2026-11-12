"""Filesystem ledger with atomic per-recipient, per-campaign claims.

``mkdir`` either creates the directory or fails because it exists, in one
kernel step. That makes it a safe claim primitive across processes, shells and
cron jobs on the same machine (and on NFS, where ``O_EXCL`` file creation is
less trustworthy).
"""

import contextlib
import json
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

try:  # POSIX only; on other platforms the per-recipient lock is skipped
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore

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

    def recent_entries(self, recipient: str, days: float) -> List[Path]:
        """Entries for ``recipient`` from ANY campaign newer than ``days`` days.

        Matches both directory claims and plain files, so ledgers written by
        older tooling keep blocking.
        """
        recipient = normalise_recipient(recipient)
        if not self.dir.is_dir():
            return []
        cutoff = time.time() - days * 86400
        suffix = f"__{recipient}"
        hits = []
        for child in self.dir.iterdir():
            if child.name.endswith(suffix) and child.stat().st_mtime > cutoff:
                hits.append(child)
        return sorted(hits)

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        """Serialise the look-back + claim step across processes.

        Two campaigns claiming the same recipient at the same instant would
        otherwise both pass the look-back before either created its claim.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        if fcntl is None:  # pragma: no cover
            yield
            return
        with open(self.dir / ".lock", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
