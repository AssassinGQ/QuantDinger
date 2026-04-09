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
    # Metals (traded as CASH on IDEALPRO)
    "XAUUSD", "XAGUSD", "XAUEUR",
}

_FOREX_SEPARATORS = "/.-_ "


def _clean_forex_raw(symbol: str) -> str:
    """Strip common separators and uppercase for Forex pair normalization."""
    result = (symbol or "").strip().upper()
    for sep in _FOREX_SEPARATORS:
        result = result.replace(sep, "")
    return result


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
    
    else:
        # Default to US stock
        return symbol, "SMART", "USD"


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
    
    # Forex: strip separators, check against known set
    forex_clean = _clean_forex_raw(symbol)
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
    return ib_symbol
