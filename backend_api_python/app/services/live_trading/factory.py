"""
Factory for direct exchange clients.

Supports:
- Crypto exchanges: Binance, OKX, Bitget, Bybit, Coinbase, Kraken, KuCoin, Gate, Bitfinex
- Traditional brokers: Interactive Brokers (IBKR) for US/HK stocks
- Forex brokers: MetaTrader 5 (MT5)

Crypto clients inherit ``BaseRestClient``; IBKR and MT5 inherit
``ExchangeEngine``.  The return type of ``create_client`` is a union
of both so the caller can use ``isinstance(client, ExchangeEngine)``
to detect engine-adapter clients.
"""

from __future__ import annotations

from typing import Any, Dict, Union

from app.services.live_trading.base import BaseRestClient, LiveTradingError
from app.services.live_trading.binance import BinanceFuturesClient
from app.services.live_trading.binance_spot import BinanceSpotClient
from app.services.live_trading.okx import OkxClient
from app.services.live_trading.bitget import BitgetMixClient
from app.services.live_trading.bitget_spot import BitgetSpotClient
from app.services.live_trading.bybit import BybitClient
from app.services.live_trading.coinbase_exchange import CoinbaseExchangeClient
from app.services.live_trading.kraken import KrakenClient
from app.services.live_trading.kraken_futures import KrakenFuturesClient
from app.services.live_trading.kucoin import KucoinSpotClient, KucoinFuturesClient
from app.services.live_trading.gate import GateSpotClient, GateUsdtFuturesClient
from app.services.live_trading.bitfinex import BitfinexClient, BitfinexDerivativesClient
from app.services.live_trading.deepcoin import DeepcoinClient


def _get(cfg: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = cfg.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def create_client(exchange_config: Dict[str, Any], *, market_type: str = "swap"):
    """Create an exchange client based on *exchange_config*.

    Returns a ``BaseRestClient`` for crypto exchanges or an
    ``ExchangeEngine`` subclass for IBKR / MT5.
    """
    if not isinstance(exchange_config, dict):
        raise LiveTradingError("Invalid exchange_config")
    exchange_id = _get(exchange_config, "exchange_id", "exchangeId").lower()
    api_key = _get(exchange_config, "api_key", "apiKey")
    secret_key = _get(exchange_config, "secret_key", "secret")
    passphrase = _get(exchange_config, "passphrase", "password")

    mt = (market_type or exchange_config.get("market_type") or exchange_config.get("defaultType") or "swap").strip().lower()
    if mt in ("futures", "future", "perp", "perpetual"):
        mt = "swap"

    if exchange_id == "binance":
        # 检查是否启用模拟交易，支持布尔值和字符串
        enable_demo = exchange_config.get("enable_demo_trading") or exchange_config.get("enableDemoTrading")
        is_demo = bool(enable_demo) if isinstance(enable_demo, bool) else str(enable_demo).lower() in ("true", "1", "yes")

        if mt == "spot":
            default_url = "https://demo-api.binance.com" if is_demo else "https://api.binance.com"
            base_url = _get(exchange_config, "base_url", "baseUrl") or default_url
            return BinanceSpotClient(api_key=api_key, secret_key=secret_key, base_url=base_url, enable_demo_trading=is_demo)
        # Default to USDT-M futures  
        default_url = "https://demo-fapi.binance.com" if is_demo else "https://fapi.binance.com"
        base_url = _get(exchange_config, "base_url", "baseUrl") or default_url
        return BinanceFuturesClient(api_key=api_key, secret_key=secret_key, base_url=base_url, enable_demo_trading=is_demo)

    if exchange_id == "okx":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://www.okx.com"
        return OkxClient(api_key=api_key, secret_key=secret_key, passphrase=passphrase, base_url=base_url)

    if exchange_id == "bitget":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.bitget.com"
        if mt == "spot":
            channel_api_code = _get(exchange_config, "channel_api_code", "channelApiCode") or "bntva"
            return BitgetSpotClient(api_key=api_key, secret_key=secret_key, passphrase=passphrase, base_url=base_url, channel_api_code=channel_api_code)
        return BitgetMixClient(api_key=api_key, secret_key=secret_key, passphrase=passphrase, base_url=base_url)

    if exchange_id == "bybit":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.bybit.com"
        category = "spot" if mt == "spot" else "linear"
        recv_window_ms = int(exchange_config.get("recv_window_ms") or exchange_config.get("recvWindow") or 5000)
        return BybitClient(api_key=api_key, secret_key=secret_key, base_url=base_url, category=category, recv_window_ms=recv_window_ms)

    if exchange_id in ("coinbaseexchange", "coinbase_exchange"):
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.exchange.coinbase.com"
        if mt != "spot":
            raise LiveTradingError("CoinbaseExchange only supports spot market_type in this project")
        return CoinbaseExchangeClient(api_key=api_key, secret_key=secret_key, passphrase=passphrase, base_url=base_url)

    if exchange_id == "kraken":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.kraken.com"
        if mt == "spot":
            return KrakenClient(api_key=api_key, secret_key=secret_key, base_url=base_url)
        # Futures/perp
        fut_url = _get(exchange_config, "futures_base_url", "futuresBaseUrl") or "https://futures.kraken.com"
        return KrakenFuturesClient(api_key=api_key, secret_key=secret_key, base_url=fut_url)

    if exchange_id == "kucoin":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.kucoin.com"
        if mt == "spot":
            return KucoinSpotClient(api_key=api_key, secret_key=secret_key, passphrase=passphrase, base_url=base_url)
        fut_url = _get(exchange_config, "futures_base_url", "futuresBaseUrl") or "https://api-futures.kucoin.com"
        return KucoinFuturesClient(api_key=api_key, secret_key=secret_key, passphrase=passphrase, base_url=fut_url)

    if exchange_id == "gate":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.gateio.ws"
        if mt == "spot":
            return GateSpotClient(api_key=api_key, secret_key=secret_key, base_url=base_url)
        # Default to USDT futures for swap
        return GateUsdtFuturesClient(api_key=api_key, secret_key=secret_key, base_url=base_url)

    if exchange_id == "bitfinex":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.bitfinex.com"
        if mt == "spot":
            return BitfinexClient(api_key=api_key, secret_key=secret_key, base_url=base_url)
        return BitfinexDerivativesClient(api_key=api_key, secret_key=secret_key, base_url=base_url)

    if exchange_id == "deepcoin":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.deepcoin.com"
        return DeepcoinClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            base_url=base_url,
            market_type=mt,
        )

    # Traditional brokers (IBKR for US/HK stocks only)
    if exchange_id == "ibkr":
        return _create_ibkr_client(exchange_config)

    # Forex brokers (MT5 for Forex only)
    if exchange_id == "mt5":
        return _create_mt5_client(exchange_config)

    raise LiveTradingError(f"Unsupported exchange_id: {exchange_id}")


# ── ExchangeEngine factories (lazy imports) ──────────────────────


def _create_ibkr_client(exchange_config: Dict[str, Any]):
    """Create or retrieve IBKR client (ExchangeEngine).

    Uses the global singleton when no strategy-level host/port is specified.
    """
    try:
        from app.services.ibkr_trading.client import IBKRClient, IBKRConfig, get_ibkr_client
    except ImportError as exc:
        raise LiveTradingError("IBKR trading requires ib_insync. Run: pip install ib_insync") from exc

    has_strategy_level_config = exchange_config.get("ibkr_host") or exchange_config.get("ibkr_port")
    if not has_strategy_level_config:
        return get_ibkr_client()

    config = IBKRConfig(
        host=str(exchange_config.get("ibkr_host") or "127.0.0.1").strip(),
        port=int(exchange_config.get("ibkr_port") or 7497),
        client_id=int(exchange_config.get("ibkr_client_id") or 1),
        account=str(exchange_config.get("ibkr_account") or "").strip(),
        readonly=False,
    )

    client = IBKRClient(config)
    if not client.connect():
        raise LiveTradingError("Failed to connect to IBKR TWS/Gateway. Please check if it's running.")
    return client


def _create_mt5_client(exchange_config: Dict[str, Any]):
    """Create or retrieve MT5 client (ExchangeEngine) for forex trading.

    Uses the global singleton when no strategy-level credentials are specified.
    """
    try:
        from app.services.mt5_trading.client import MT5Client, MT5Config, get_mt5_client
    except ImportError as exc:
        raise LiveTradingError(
            "MT5 trading requires MetaTrader5 library. Run: pip install MetaTrader5\n"
            "Note: This library only works on Windows."
        ) from exc

    has_strategy_level_config = (
        exchange_config.get("mt5_login")
        or exchange_config.get("mt5_server")
    )
    if not has_strategy_level_config:
        return get_mt5_client()

    login = int(exchange_config.get("mt5_login") or 0)
    password = str(exchange_config.get("mt5_password") or "").strip()
    server = str(exchange_config.get("mt5_server") or "").strip()
    terminal_path = str(exchange_config.get("mt5_terminal_path") or "").strip()

    if not login or not password or not server:
        raise LiveTradingError("MT5 requires login, password, and server")

    config = MT5Config(
        login=login,
        password=password,
        server=server,
        terminal_path=terminal_path,
    )

    client = MT5Client(config)
    if not client.connect():
        raise LiveTradingError(
            "Failed to connect to MT5 terminal. Please check:\n"
            "1. MT5 terminal is running\n"
            "2. Credentials are correct\n"
            "3. You are on Windows"
        )
    return client
