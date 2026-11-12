"""Command line interface.

    send-guard claim <campaign> <recipient> [--days N] [--check-cmd CMD]
    send-guard release <campaign> <recipient>
    send-guard status <recipient> [--days N]
    send-guard run <campaign> <recipient> [--days N] [--check-cmd CMD] -- <command...>

Exit codes for ``claim`` and ``run``: 0 claimed, 2 usage, 3 ledger hit,
4 found by check, 5 check failed. ``run`` returns the command's own exit code
when the claim succeeded.
"""

import argparse
import json
import subprocess
import sys
from typing import List, Optional

from . import __version__
from .guard import DEFAULT_DAYS, Guard, Status, command_check
from .keys import InvalidKey, normalise_recipient, validate_campaign
from .ledger import Claim, Ledger


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="send-guard", description="Claim a recipient before you email them.")
    p.add_argument("--version", action="version", version=f"send-guard {__version__}")
    p.add_argument("--ledger", help="ledger directory (default: $SEND_GUARD_LEDGER or ./.send-guard)")
    p.add_argument("--json", action="store_true", help="print machine-readable output")
    sub = p.add_subparsers(dest="command", required=True)

    def window(sp):
        sp.add_argument("--days", type=float, default=DEFAULT_DAYS, help="look-back window in days (default 7)")

    claim = sub.add_parser("claim", help="look back, then atomically claim campaign+recipient")
    claim.add_argument("campaign")
    claim.add_argument("recipient")
    window(claim)
    claim.add_argument("--check-cmd", help="command run after the claim; exit 0 clear, 10 found, else failed")
    claim.add_argument("--check-timeout", type=float, default=300.0)

    release = sub.add_parser("release", help="give a claim back (only if nothing was sent)")
    release.add_argument("campaign")
    release.add_argument("recipient")

    status = sub.add_parser("status", help="list ledger entries for a recipient inside the window")
    status.add_argument("recipient")
    window(status)

    run = sub.add_parser("run", help="claim, then run a command; the claim stays whatever the command does")
    run.add_argument("campaign")
    run.add_argument("recipient")
    window(run)
    run.add_argument("--check-cmd")
    run.add_argument("--check-timeout", type=float, default=300.0)
    run.add_argument("argv", nargs=argparse.REMAINDER, help="-- command to run if the claim succeeds")
    return p


def _emit(args, payload: dict, text: str) -> None:
    print(json.dumps(payload) if args.json else text)


def _claim(args, ledger: Ledger):
    check = command_check(args.check_cmd, args.check_timeout) if args.check_cmd else None
    decision = Guard(ledger, check=check, days=args.days).acquire(args.campaign, args.recipient)
    _emit(
        args,
        {
            "ok": decision.ok,
            "status": decision.status.name,
            "campaign": decision.campaign,
            "recipient": decision.recipient,
            "message": decision.message,
            "blockers": decision.blockers,
        },
        ("OK " if decision.ok else "BLOCKED ") + decision.message,
    )
    return decision


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    ledger = Ledger(args.ledger)
    try:
        if args.command == "claim":
            return int(_claim(args, ledger).status)

        if args.command == "run":
            command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            if not command:
                print("run needs a command after --", file=sys.stderr)
                return int(Status.USAGE)
            decision = _claim(args, ledger)
            if not decision.ok:
                return int(decision.status)
            return subprocess.call(command)

        if args.command == "release":
            campaign = validate_campaign(args.campaign)
            recipient = normalise_recipient(args.recipient)
            path = ledger.path_for(campaign, recipient)
            if not path.is_dir():
                _emit(args, {"released": False}, "nothing to release")
                return 1
            Guard(ledger).release(Claim(campaign, recipient, path))
            _emit(args, {"released": True}, f"released {path.name}")
            return 0

        if args.command == "status":
            hits = ledger.recent_entries(args.recipient, args.days)
            _emit(args, {"entries": [h.name for h in hits]}, "\n".join(h.name for h in hits) or "clear")
            return 3 if hits else 0
    except InvalidKey as exc:
        print(f"send-guard: {exc}", file=sys.stderr)
        return int(Status.USAGE)
    return int(Status.USAGE)


if __name__ == "__main__":
    sys.exit(main())
