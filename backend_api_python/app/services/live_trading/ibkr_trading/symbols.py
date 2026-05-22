"""
Symbol Mapping and Conversion

Converts QuantDinger system symbols to IB contract format.
"""

from typing import Tuple, Optional

KNOWN_FOREX_PAIRS = {
    # Major pairs
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    # Cross pairs
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "NZDJPY", "NZDCHF", "NZDCAD",
    "CADJPY", "CADCHF", "CHFJPY",
    # Exotic (common on IDEALPRO)
    "USDMXN", "USDZAR", "USDTRY", "USDHKD", "USDSGD",
    "USDNOK", "USDSEK", "USDDKK",
    "EURTRY", "EURMXN", "EURNOK", "EURSEK", "EURDKK", "EURPLN", "EURHUF", "EURCZK",
    # Precious metals (XAU*/XAG* six-letter pairs) use CMDTY on SMART — not IDEALPRO CASH; see parse_symbol / Metals branch.
}

_FOREX_SEPARATORS = "/.-_ "


def _clean_forex_raw(symbol: str) -> str:
    """Strip common separators and uppercase for Forex pair normalization."""
    result = (symbol or "").strip().upper()
    for sep in _FOREX_SEPARATORS:
        result = result.replace(sep, "")
    return result


def _is_precious_metal_pair(forex_clean: str) -> bool:
    """True for validated six-letter XAU*/XAG* pairs routed as Metals (excludes XAUEUR per IBKR CMDTY behavior)."""
    if len(forex_clean) != 6 or not forex_clean.isalpha():
        return False
    if forex_clean == "XAUEUR":
        return False
    return forex_clean.startswith("XAU") or forex_clean.startswith("XAG")


def resolve_ibkr_market_type(symbol: str, market_category: str) -> str:
    """QD ``Forex`` + XAU/XAG spot pair -> ``Metals`` for IBKR; else pass-through."""
    cat = (market_category or "").strip()
    if cat == "Forex":
        pair = _clean_forex_raw(symbol)
        if _is_precious_metal_pair(pair):
            return "Metals"
    return cat


def normalize_symbol(symbol: str, market_type: str) -> Tuple[str, str, str]:
    """
    Convert system symbol to IB contract parameters.
    
    Args:
        symbol: Symbol code in the system
        market_type: Market type (USStock, HShare)
        
    Returns:
        (ib_symbol, exchange, currency)
    """
    symbol = (symbol or "").strip().upper()
    market_type = (market_type or "").strip()
    
    if market_type == "Forex":
        pair = _clean_forex_raw(symbol)
        if len(pair) != 6 or not pair.isalpha():
            raise ValueError(
                f"Invalid Forex symbol '{symbol}': "
                f"expected 6 letters after cleaning (e.g. EURUSD), got '{pair}'"
            )
        return pair, "IDEALPRO", pair[3:]

    elif market_type == "Metals":
        pair = _clean_forex_raw(symbol)
        if len(pair) != 6 or not pair.isalpha():
            raise ValueError(
                f"Invalid precious metals symbol '{symbol}': "
                f"expected 6 letters after cleaning (e.g. XAUUSD), got '{pair}'"
            )
        return pair, "SMART", pair[3:6]

    elif market_type == "USStock":
        # US stocks: AAPL, TSLA, GOOGL
        # Use SMART routing for best execution
        return symbol, "SMART", "USD"

    elif market_type == "HShare":
        # Hong Kong stock formats:
        # - 0700.HK -> 700
        # - 00700 -> 700
        # - 700 -> 700
        ib_symbol = symbol

        # Remove .HK suffix
        if ib_symbol.endswith(".HK"):
            ib_symbol = ib_symbol[:-3]

        # Remove leading zeros
        ib_symbol = ib_symbol.lstrip("0") or "0"

        return ib_symbol, "SEHK", "HKD"

    elif market_type == "IndexETF":
        # Index ETFs: routed by currency just like the data-source layer.
        # - 6-digit numeric, prefix 5/1  -> A-share ETF (not actually tradable
        #   via IBKR US gateway; we still produce a contract for symmetry; the
        #   primary_exchange resolver will return None and IBKR will reject).
        # - 4-5 digit numeric            -> HK ETF on SEHK
        # - alpha ticker (QQQ/SPY/...)   -> US ETF on SMART; primary_exchange
        #   MUST be supplied by caller (see resolve_primary_exchange) so IBKR
        #   can resolve the NBBO listing.
        if symbol.isdigit():
            if len(symbol) == 6:
                # A-share ETF: route placeholder; live trading not supported.
                return symbol, "SEHKNTL", "CNH"
            if 1 <= len(symbol) <= 5:
                # HK ETF: strip leading zeros, route through SEHK.
                ib_symbol = symbol.lstrip("0") or "0"
                return ib_symbol, "SEHK", "HKD"
        # US ETF default. The caller MUST also call resolve_primary_exchange().
        return symbol, "SMART", "USD"

    else:
        # Default to US stock
        return symbol, "SMART", "USD"


def resolve_primary_exchange(symbol: str, market_type: str) -> Optional[str]:
    """Return the IBKR primaryExchange for a contract, or ``None`` if not needed.

    Background
    ----------
    For ambiguous tickers (most notably US ETFs like QQQ/SPY where the same
    symbol trades on multiple venues), IBKR's SMART router cannot uniquely
    resolve the contract and ``reqMktData`` returns an empty ticker. The fix
    is to pass ``primaryExchange`` so SMART knows which listing to use.

    This helper looks up the canonical primary exchange from the
    ``qd_market_symbols`` seed table (column ``exchange``).

    Returns
    -------
    str | None
        - For ``market_type == 'IndexETF'``: the value of ``exchange`` from
          ``qd_market_symbols`` (e.g. 'NASDAQ' for QQQ, 'ARCA' for SPY,
          'SEHK' for 02800). Falls back to 'ARCA' for unknown US ETFs so
          the caller can still build a contract.
        - For all other market types: ``None`` (current behavior preserved).

    DB / config failures are swallowed and treated as a miss; this function
    must never raise.
    """
    mt = (market_type or "").strip()
    if mt != "IndexETF":
        return None

    sym = (symbol or "").strip().upper()
    if not sym:
        return None

    # HK ETF (2-5 digit numeric, often padded) → SEHK regardless of DB lookup.
    if sym.isdigit() and 1 <= len(sym) <= 5:
        return "SEHK"

    # A-share ETF (6 digit numeric): IBKR can't trade these; return None so
    # caller can decide whether to error out or skip primaryExchange.
    if sym.isdigit() and len(sym) == 6:
        return None

    # Alpha ticker → look up qd_market_symbols.exchange.
    try:
        from app.utils.db import get_db_connection
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT exchange FROM qd_market_symbols "
                "WHERE market = %s AND symbol = %s LIMIT 1",
                ("IndexETF", sym),
            )
            row = cur.fetchone()
            cur.close()
            if row:
                # row may be dict-like (RealDictCursor) or tuple-like.
                exch = row.get("exchange") if hasattr(row, "get") else row[0]
                exch = (exch or "").strip()
                if exch:
                    return exch
    except Exception:  # noqa: BLE001 — DB unreachable / schema mismatch
        # Treat any failure as a miss; let the default kick in.
        pass

    # Default: ARCA covers most US-listed ETFs.
    return "ARCA"


def parse_symbol(symbol: str) -> Tuple[str, Optional[str]]:
    """
    Parse symbol and auto-detect market type.
    
    Args:
        symbol: Symbol code
        
    Returns:
        (clean_symbol, market_type)
    """
    symbol = (symbol or "").strip().upper()
    
    # HK stock: ends with .HK or all digits
    if symbol.endswith(".HK"):
        return symbol, "HShare"
    
    # All digits (likely HK stock code)
    clean = symbol.lstrip("0")
    if clean.isdigit() and len(clean) <= 5:
        return symbol, "HShare"
    
    forex_clean = _clean_forex_raw(symbol)
    if _is_precious_metal_pair(forex_clean):
        return forex_clean, "Metals"
    if forex_clean in KNOWN_FOREX_PAIRS:
        return forex_clean, "Forex"
    
    # Default to US stock
    return symbol, "USStock"


def format_display_symbol(ib_symbol: str, exchange: str) -> str:
    """
    Convert IB contract format back to display format.
    
    Args:
        ib_symbol: IB symbol
        exchange: Exchange code
        
    Returns:
        Display symbol
    """
    if exchange == "SEHK":
        # HK stock: pad to 4 digits, add .HK
        padded = ib_symbol.zfill(4)
        return f"{padded}.HK"
    if exchange == "IDEALPRO":
        if len(ib_symbol) == 6 and ib_symbol.isalpha():
            return f"{ib_symbol[:3]}.{ib_symbol[3:]}"
        return ib_symbol
    if (
        exchange == "SMART"
        and len(ib_symbol) == 6
        and ib_symbol.isalpha()
        and (ib_symbol.startswith("XAU") or ib_symbol.startswith("XAG"))
    ):
        return ib_symbol
    return ib_symbol
