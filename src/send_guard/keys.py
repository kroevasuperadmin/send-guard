"""Normalisation and validation of campaign names and recipients.

A ledger entry is a directory named ``<campaign>__<recipient>``. Both parts
end up in a file name, so anything that could escape the ledger directory or
break the ``__`` separator is rejected up front.
"""

import re

SEPARATOR = "__"
_CAMPAIGN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RECIPIENT_RE = re.compile(r"^[^@\s/\\]+@[^@\s/\\]+\.[^@\s/\\]+$")


class InvalidKey(ValueError):
    """Raised when a campaign or recipient cannot be used as a ledger key."""


def normalise_recipient(recipient: str) -> str:
    """Lowercase and strip whitespace, then validate as ``local@domain.tld``."""
    value = "".join(str(recipient).split()).lower()
    if not _RECIPIENT_RE.match(value) or ".." in value:
        raise InvalidKey("recipient must look like name@example.com")
    if SEPARATOR in value:
        raise InvalidKey("recipient must not contain '__'")
    return value


def validate_campaign(campaign: str) -> str:
    value = str(campaign).strip()
    if not _CAMPAIGN_RE.match(value) or ".." in value:
        raise InvalidKey(
            "campaign may only use letters, digits, '.', '_' and '-' and must start with a letter or digit"
        )
    if SEPARATOR in value:
        raise InvalidKey("campaign must not contain '__'")
    return value


def entry_name(campaign: str, recipient: str) -> str:
    return f"{validate_campaign(campaign)}{SEPARATOR}{normalise_recipient(recipient)}"
