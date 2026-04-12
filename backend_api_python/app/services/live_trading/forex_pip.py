"""Pip size helpers for Forex/Metals automation (slippage cap → limit price)."""


def pip_size_for_forex_symbol(symbol: str) -> float:
    """Return one pip in price units for *symbol* (IDEALPRO-style naming)."""
    s = (symbol or "").upper()
    if "JPY" in s:
        return 0.01
    return 0.0001
