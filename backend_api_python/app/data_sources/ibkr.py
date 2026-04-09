"""
IBKR 数据源
从 Interactive Brokers Gateway 获取 K线和实时报价
"""
import logging
import os
from typing import Any, Dict, List, Optional

from app.data_sources.base import BaseDataSource
from app.data_sources.rate_limiter import get_ibkr_limiter
from app.services import kline_fetcher
from app.services.live_trading.ibkr_trading.client import get_ibkr_client, IBKRConfig

logger = logging.getLogger(__name__)


class IBKRDataSource(BaseDataSource):
    """IBKR 数据源"""

    name: str = "ibkr"

    def __init__(
        self,
        mode: Optional[str] = None,  # paper/live
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
    ):
        """
        初始化 IBKRDataSource

        Args:
            mode: IBKR 模式 (paper/live)
            host: IBKR Gateway 主机地址
            port: IBKR Gateway 端口
            client_id: IBKR 客户端 ID
        """
        self._mode = mode or os.environ.get("IBKR_MODE", "paper")
        self._host = host or os.environ.get("IBKR_HOST", "ib-live-gateway")
        self._port = port or int(os.environ.get("IBKR_PORT", "4003"))
        self._client_id = client_id or int(os.environ.get("IBKR_CLIENT_ID", "1"))
        self._market_type = "USStock"

        self._config = IBKRConfig(
            host=self._host,
            port=self._port,
            client_id=self._client_id,
        )
        self._client: Optional[Any] = None
        self._pending_requests: Dict[int, Any] = {}
        self._rate_limiter = get_ibkr_limiter()

    @property
    def client(self):
        """Get or create internal IBKRClient instance"""
        if self._client is None:
            cfg = IBKRConfig.from_env(self._mode)
            self._client = get_ibkr_client(cfg, mode=self._mode)
        return self._client

    def connect(self, timeout: float = 60) -> bool:
        """
        建立与 IBKR Gateway 的连接（延迟连接）

        Args:
            timeout: 连接超时时间（秒）

        Returns:
            连接是否成功
        """
        try:
            return self.client.connect(timeout=timeout)
        except Exception as e:
            logger.exception("Failed to connect to IBKR Gateway")
            return False

    def is_connected(self) -> bool:
        """
        检查连接状态

        Returns:
            是否已连接
        """
        if self._client is None:
            return False
        return self.client.connected

    def disconnect(self) -> None:
        """
        断开与 IBKR Gateway 的连接
        """
        if self._client is not None:
            self._client.disconnect()
            self._client = None

    def reconnect(self, max_retries: int = 3) -> bool:
        """
        重新连接 IBKR Gateway

        Args:
            max_retries: 最大重试次数

        Returns:
            重连是否成功
        """
        if self._client is not None:
            return self._client.reconnect(max_retries=max_retries)
        # 如果之前没有连接过，直接尝试连接
        return self.connect()

    def get_kline(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        before_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取K线数据

        Args:
            symbol: 股票代码 (例如: AAPL, MSFT)
            timeframe: 时间周期 (1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W)
            limit: 数据条数
            before_time: 获取此时间之前的数据（Unix时间戳，秒）

        Returns:
            K线数据列表
        """
        # Per D-19: Check cache first (database 1m -> database 5m -> database kline -> network)
        # IBKR data source uses USStock market for caching
        try:
            cached_klines = kline_fetcher.get_kline(
                market="USStock",
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                before_time=before_time
            )
            if cached_klines and len(cached_klines) >= limit:
                logger.debug(f"Using cached klines for {symbol} {timeframe}")
                return cached_klines
        except Exception as e:
            logger.debug(f"Cache check failed for {symbol}: {e}")

        # Proceed to network call if cache miss
        # Per D-23: Acquire rate limiter before API call
        self._rate_limiter.acquire(request_type="hist", symbol=symbol)

        try:
            # Use internal get_historical_bars method per D-28
            bars = self.client.get_historical_bars(symbol, timeframe, limit, before_time)

            # Apply filter and limit
            result = self.filter_and_limit(bars, limit, before_time)

            # Record log
            self.log_result(symbol, result, timeframe)

            return result

        except Exception as e:
            logger.error(f"Failed to get kline for {symbol}: {e}")
            return []

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时报价

        Per D-20: No caching - always fetch fresh data from IBKR Gateway.

        Args:
            symbol: 股票代码

        Returns:
            报价数据字典，包含 'last' 键
        """
        # Per D-22: Acquire rate limiter before API call
        self._rate_limiter.acquire(request_type="hist", symbol=symbol)

        try:
            # Use internal get_quote method per D-35
            quote = self.client.get_quote(symbol, self._market_type)

            if quote.get("success", False):
                return {
                    "symbol": symbol,
                    "last": quote.get("last", 0),
                }
            else:
                logger.warning(f"Failed to get quote for {symbol}: {quote.get('error')}")
                return {'last': 0, 'symbol': symbol}

        except Exception as e:
            logger.warning(f"Failed to get ticker for {symbol}: {e}")
            # Per D-20 fallback: return fallback with last=0
            return {'last': 0, 'symbol': symbol}
