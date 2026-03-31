"""
Factory for direct exchange clients and runners.

Supports:
- Crypto exchanges: Binance, OKX, Bitget, Bybit, Coinbase, Kraken, KuCoin, Gate, Bitfinex
- Traditional brokers: Interactive Brokers (IBKR) for US/HK stocks
- Forex brokers: MetaTrader 5 (MT5)

Crypto clients inherit ``BaseRestfulClient``; IBKR and MT5 inherit
``BaseStatefulClient``.
"""

from __future__ import annotations

from typing import Any, Dict, Union

from app.services.live_trading.base import BaseRestfulClient, BaseStatefulClient, LiveTradingError
from app.services.live_trading.crypto_trading.binance import BinanceFuturesClient
from app.services.live_trading.crypto_trading.binance_spot import BinanceSpotClient
from app.services.live_trading.crypto_trading.okx import OkxClient
from app.services.live_trading.crypto_trading.bitget import BitgetMixClient
from app.services.live_trading.crypto_trading.bitget_spot import BitgetSpotClient
from app.services.live_trading.crypto_trading.bybit import BybitClient
from app.services.live_trading.crypto_trading.coinbase_exchange import CoinbaseExchangeClient
from app.services.live_trading.crypto_trading.kraken import KrakenClient
from app.services.live_trading.crypto_trading.kraken_futures import KrakenFuturesClient
from app.services.live_trading.crypto_trading.kucoin import KucoinSpotClient, KucoinFuturesClient
from app.services.live_trading.crypto_trading.gate import GateSpotClient, GateUsdtFuturesClient
from app.services.live_trading.crypto_trading.bitfinex import BitfinexClient, BitfinexDerivativesClient
from app.services.live_trading.crypto_trading.deepcoin import DeepcoinClient


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

    Returns a ``BaseRestfulClient`` for crypto exchanges or a
    ``BaseStatefulClient`` subclass for IBKR / MT5.
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
    if exchange_id in ("ibkr", "ibkr-paper", "ibkr-live"):
        return _create_ibkr_client(exchange_config, exchange_id=exchange_id)

    # Forex brokers (MT5 for Forex only)
    if exchange_id == "mt5":
        return _create_mt5_client(exchange_config)

    # Hong Kong / US / A-share broker (uSMART)
    if exchange_id == "usmart":
        return _create_usmart_client(exchange_config)

    # EastMoney (东方财富) broker
    if exchange_id == "eastmoney":
        return _create_ef_client(exchange_config)

    raise LiveTradingError(f"Unsupported exchange_id: {exchange_id}")


# ── get_runner ────────────────────────────────────────────────────


def get_runner(client):
    """Return the appropriate OrderRunner for the given client instance."""
    from app.services.live_trading.runners import (
        OrderRunner, RestfulClientRunner, StatefulClientRunner,
    )
    if isinstance(client, BaseStatefulClient):
        return StatefulClientRunner()
    if isinstance(client, BaseRestfulClient):
        return RestfulClientRunner()
    raise LiveTradingError(f"No runner for client type: {type(client)}")


# ── BaseStatefulClient factories (lazy imports) ──────────────────


def _parse_ibkr_mode(exchange_id: str, exchange_config: Dict[str, Any]) -> str:
    """Derive IBKR gateway mode from exchange_id, falling back to ibkr_mode config."""
    if exchange_id == "ibkr-live":
        return "live"
    if exchange_id == "ibkr-paper":
        return "paper"
    return exchange_config.get("ibkr_mode", "paper")


def _create_ibkr_client(exchange_config: Dict[str, Any], *, exchange_id: str = "ibkr"):
    """Create or retrieve IBKR client (BaseStatefulClient).

    Uses exchange_id (ibkr-paper / ibkr-live) to select the global singleton.
    Falls back to ibkr_mode config for legacy exchange_id="ibkr".
    """
    try:
        from app.services.live_trading.ibkr_trading.client import IBKRClient, IBKRConfig, get_ibkr_client
    except ImportError as exc:
        raise LiveTradingError("IBKR trading requires ib_insync. Run: pip install ib_insync") from exc

    mode = _parse_ibkr_mode(exchange_id, exchange_config)

    has_strategy_level_config = exchange_config.get("ibkr_host") or exchange_config.get("ibkr_port")
    if not has_strategy_level_config:
        return get_ibkr_client(mode=mode)

    config = IBKRConfig(
        host=str(exchange_config.get("ibkr_host") or "127.0.0.1").strip(),
        port=int(exchange_config.get("ibkr_port") or 7497),
        client_id=int(exchange_config.get("ibkr_client_id") or 1),
        account=str(exchange_config.get("ibkr_account") or "").strip(),
        readonly=False,
    )

    client = IBKRClient(config, mode=mode)
    if not client.connect():
        raise LiveTradingError("Failed to connect to IBKR TWS/Gateway. Please check if it's running.")
    return client


def _create_mt5_client(exchange_config: Dict[str, Any]):
    """Create or retrieve MT5 client (BaseStatefulClient) for forex trading.

    Uses the global singleton when no strategy-level credentials are specified.
    """
    try:
        from app.services.live_trading.mt5_trading.client import MT5Client, MT5Config, get_mt5_client
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


def _create_usmart_client(exchange_config: Dict[str, Any]):
    """Create uSMART client (BaseStatefulClient) for HK/US/A-share trading."""
    try:
        from app.services.live_trading.usmart_trading.config import USmartConfig
        from app.services.live_trading.usmart_trading.client import USmartClient
    except ImportError as exc:
        raise LiveTradingError("uSMART trading requires rsa library. Run: pip install rsa") from exc

    config = USmartConfig(
        channel_id=_get(exchange_config, "channel_id", "channelId"),
        private_key=_get(exchange_config, "private_key", "privateKey"),
        public_key=_get(exchange_config, "public_key", "publicKey"),
        phone_number=_get(exchange_config, "phone_number", "phoneNumber"),
        password=_get(exchange_config, "password"),
        area_code=_get(exchange_config, "area_code", "areaCode") or "86",
        base_url=_get(exchange_config, "base_url", "baseUrl") or "https://open-jy.yxzq.com",
    )

    client = USmartClient(config)
    if not client.connect():
        raise LiveTradingError("Failed to connect to uSMART. Please check credentials.")
    return client


def _create_ef_client(exchange_config: Dict[str, Any]):
    """Create EastMoney (东方财富) client for A-share/HK-stock/bond/ETF trading."""
    from app.services.live_trading.ef_trading.config import EFConfig
    from app.services.live_trading.ef_trading.client import EFClient

    config = EFConfig(
        account_id=_get(exchange_config, "account_id", "accountId"),
        password=_get(exchange_config, "password"),
        market=_get(exchange_config, "market") or "ab",
        token=_get(exchange_config, "token") or "",
        base_url=_get(exchange_config, "base_url", "baseUrl") or "",
    )

    client = EFClient(config)
    if not client.connect():
        raise LiveTradingError("Failed to connect to EastMoney. Please check credentials.")
    return client
