# send-guard

A small CLI and Python library that refuses a send when the same address was contacted recently. Before each send you ask it for a claim on `campaign + recipient`. It grants a claim only when its ledger, and any check you configure, show no recent contact with that address.

## Why

Two cron jobs, a retry after a timeout, or two agents working the same list can each send the same cold email. A mailbox check sees mail sent by hand but lags behind sends still in flight. A ledger sees in-flight sends but knows nothing about mail sent by hand.

send-guard combines a ledger with a mailbox check in three steps.

1. **Look-back.** It refuses if the recipient has an entry from any campaign inside the window (default 7 days).
2. **Atomic claim.** It creates `<campaign>__<recipient>` with `mkdir`. Exactly one process wins, even when 16 start at once.
3. **Check hook.** It runs your command, usually a Sent-folder lookup. If the recipient is found, the claim stays and the send is refused. If the check cannot run, the guard fails closed: it releases the claim and refuses, because nothing was sent.

The ledger is a plain directory with one folder per claim, so it works with cron, shell scripts and any language. POSIX file locking is used to serialise steps 1 and 2; on Windows the claim is still atomic but the cross-campaign check can race.

## Install

```sh
pip install git+https://github.com/kroevasuperadmin/send-guard
```

Python 3.9+, standard library only.

## Usage

```sh
send-guard claim <campaign> <recipient> [--days 7] [--check-cmd CMD]
send-guard run   <campaign> <recipient> [--days 7] [--check-cmd CMD] -- <send command...>
send-guard status  <recipient> [--days 7]
send-guard release <campaign> <recipient>
```

The ledger lives in `./.send-guard`, or wherever `--ledger` or `$SEND_GUARD_LEDGER` points. Add `--json` for machine-readable output.

Exit codes for `claim` and `run`:

| code | meaning |
|------|---------|
| 0 | claimed, go ahead and send |
| 2 | bad input or usage |
| 3 | blocked by the ledger (same claim, or any campaign inside the window) |
| 4 | the check hook found the recipient |
| 5 | the check hook could not run; claim released, nothing sent |

`run` executes your command only after a successful claim, and returns the command's exit code. The claim is kept whatever the command does. If a send fails halfway you cannot know whether the message left, so retries are a human decision (`send-guard release` when you are sure).

### Check hooks

`--check-cmd` runs a command with `SEND_GUARD_CAMPAIGN`, `SEND_GUARD_RECIPIENT` and `SEND_GUARD_DAYS` in its environment. Exit 0 means clear, exit 10 means found, anything else means failed. The first line of stdout ends up in the claim folder.

A ready-made hook searches an IMAP Sent folder:

```sh
export IMAP_HOST=imap.example.com IMAP_USER=me@example.com IMAP_PASSWORD=...
send-guard claim spring-launch ada@example.com --check-cmd "python -m send_guard.imap_check"
```

### Library

```python
from send_guard import Guard, Ledger, CheckResult

def in_crm(campaign, recipient, days):
    return CheckResult(found=recipient in my_crm_contacts(days), detail="already in CRM")

guard = Guard(Ledger(".send-guard"), check=in_crm, days=7)
decision = guard.acquire("spring-launch", "ada@example.com")
if decision.ok:
    send_email(...)
else:
    print(decision.status.name, decision.message)
```

## Example

```console
$ send-guard claim spring-launch ada@example.com
OK claimed
$ send-guard claim spring-launch ada@example.com ; echo $?
BLOCKED blocked by ledger: spring-launch__ada@example.com is newer than 7 days
3
$ send-guard claim follow-up Ada@Example.com ; echo $?
BLOCKED blocked by ledger: spring-launch__ada@example.com is newer than 7 days
3
$ send-guard run weekly bob@example.com -- ./send_mail.sh bob@example.com
OK claimed
sent
```

Every decision is also appended to `guard.log` in the ledger directory as one JSON line.

## Tests

```sh
python -m unittest discover -s tests
```

## License

MIT
