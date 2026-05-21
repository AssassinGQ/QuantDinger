"""
US stock symbol normalization for QuantDinger K-line / USStock compatibility.

Dotted share-class tickers (e.g. Yahoo/Nasdaq style ``BRK.B``) are mapped to
hyphen form ``BRK-B``, matching typical QD ``USStock`` symbol formatting.
"""

import re

_CLASS_SHARE_DOT = re.compile(r"^([A-Z0-9]+)\.([A-Z]{1,2})$")


def normalize_us_stock_symbol(raw: str) -> str:
    """
    Strip, uppercase, and map class shares (``ROOT.X`` → ``ROOT-X``).

    Empty or whitespace-only input returns ``""`` without raising.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    s = s.upper()
    m = _CLASS_SHARE_DOT.match(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s
