"""The guard: look-back, atomic claim, then an optional external check.

Order matters:

1. Under the ledger lock, refuse if the recipient has any entry (any campaign)
   inside the look-back window, then claim ``<campaign>__<recipient>``.
2. Outside the lock, run the check hook (typically "is this address already in
   my mailbox's Sent folder?"). The claim is already held, so nobody else can
   start a send to the same person while a slow check runs.
3. The hook has three outcomes. Clear keeps the claim. Found keeps the claim and
   leaves a marker. Error releases the claim and refuses: the guard fails closed,
   and since nothing was sent the claim is safe to give back.
"""

import enum
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .keys import normalise_recipient, validate_campaign
from .ledger import Claim, Ledger

DEFAULT_DAYS = 7.0
FOUND_EXIT_CODE = 10


class Status(enum.IntEnum):
    CLAIMED = 0
    USAGE = 2
    LEDGER_HIT = 3
    FOUND_BY_CHECK = 4
    CHECK_FAILED = 5


@dataclass
class CheckResult:
    found: bool
    detail: str = ""


# A check receives (campaign, recipient, days) and returns a CheckResult.
# Any exception it raises counts as "the check could not run".
Check = Callable[[str, str, float], CheckResult]


@dataclass
class Decision:
    status: Status
    campaign: str
    recipient: str
    message: str
    claim: Optional[Claim] = None
    blockers: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == Status.CLAIMED


class Guard:
    def __init__(self, ledger: Ledger, check: Optional[Check] = None, days: float = DEFAULT_DAYS):
        self.ledger = ledger
        self.check = check
        self.days = days

    def acquire(self, campaign: str, recipient: str) -> Decision:
        campaign = validate_campaign(campaign)
        recipient = normalise_recipient(recipient)

        with self.ledger.lock():
            recent = self.ledger.recent_entries(recipient, self.days)
            if recent:
                names = [p.name for p in recent]
                return Decision(
                    Status.LEDGER_HIT, campaign, recipient,
                    f"blocked by ledger: {names[0]} is newer than {self.days:g} days",
                    blockers=names,
                )
            claim = self.ledger.claim(campaign, recipient)
            if claim is None:
                return Decision(Status.LEDGER_HIT, campaign, recipient, "blocked: claim already exists")

        if self.check is None:
            return Decision(Status.CLAIMED, campaign, recipient, "claimed", claim=claim)

        try:
            result = self.check(campaign, recipient, self.days)
        except Exception as exc:  # fail closed on anything the hook throws
            self.release(claim)
            return Decision(
                Status.CHECK_FAILED, campaign, recipient,
                f"check could not run, claim released, nothing sent: {exc}",
            )
        if result.found:
            (claim.path / "BLOCKED_found_by_check.txt").write_text(result.detail + "\n", encoding="utf-8")
            return Decision(
                Status.FOUND_BY_CHECK, campaign, recipient,
                f"blocked by check: {result.detail or 'recipient found'}", claim=claim,
            )
        if result.detail:
            (claim.path / "check.txt").write_text(result.detail + "\n", encoding="utf-8")
        return Decision(Status.CLAIMED, campaign, recipient, "claimed", claim=claim)

    def release(self, claim: Claim) -> None:
        """Give a claim back. Only for the case where nothing was sent."""
        shutil.rmtree(claim.path, ignore_errors=True)


def command_check(command: str, timeout: float = 300.0) -> Check:
    """Build a check from an external command (no shell is involved).

    The command gets SEND_GUARD_CAMPAIGN, SEND_GUARD_RECIPIENT and
    SEND_GUARD_DAYS in its environment. Exit 0 means clear, exit 10 means the
    recipient was found, anything else (or a timeout) means the check failed.
    The first line of stdout is kept as the detail.
    """
    argv = shlex.split(command)
    if not argv:
        raise ValueError("empty check command")

    def run(campaign: str, recipient: str, days: float) -> CheckResult:
        env = dict(os.environ)
        env.update(
            SEND_GUARD_CAMPAIGN=campaign,
            SEND_GUARD_RECIPIENT=recipient,
            SEND_GUARD_DAYS=f"{days:g}",
        )
        proc = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout)
        lines = proc.stdout.strip().splitlines()
        detail = lines[0] if lines else ""
        if proc.returncode == 0:
            return CheckResult(False, detail)
        if proc.returncode == FOUND_EXIT_CODE:
            return CheckResult(True, detail)
        raise RuntimeError(f"check exited {proc.returncode}: {proc.stderr.strip()[:200] or detail}")

    return run
