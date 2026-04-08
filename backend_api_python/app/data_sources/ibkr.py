"""
IBKR 数据源
从 Interactive Brokers Gateway 获取 K线和实时报价
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ibkr_datafetcher.config import GatewayConfig
from ibkr_datafetcher.ibkr_client import IBKRClient
from ibkr_datafetcher.types import KlineBar, SymbolConfig, Timeframe, resolve_timeframe

from app.data_sources.base import BaseDataSource
from app.services import kline_fetcher

logger = logging.getLogger(__name__)


class IBKRDataSource(BaseDataSource):
    """IBKR 数据源"""

    name: str = "ibkr"

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
    ):
        """
        初始化 IBKRDataSource

        Args:
            host: IBKR Gateway 主机地址
            port: IBKR Gateway 端口
            client_id: IBKR 客户端 ID
        """
        self._host = host or os.environ.get("IBKR_HOST", "ib-live-gateway")
        self._port = port or int(os.environ.get("IBKR_PORT", "4003"))
        self._client_id = client_id or int(os.environ.get("IBKR_CLIENT_ID", "1"))

        self._config = GatewayConfig(
            host=self._host,
            port=self._port,
            client_id=self._client_id,
        )
        self._client: Optional[IBKRClient] = None
        self._pending_requests: Dict[int, Any] = {}

    @property
    def client(self) -> IBKRClient:
        """获取或创建 IBKR 客户端实例"""
        if self._client is None:
            self._client = IBKRClient(self._config)
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
        return self._client.is_connected()

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
        if not self.is_connected():
            if not self.connect():
                logger.error("Failed to connect to IBKR Gateway")
                return []

        try:
            # 确保连接
            if not self.is_connected():
                self.connect()

            # 创建合约配置
            symbol_config = SymbolConfig(
                symbol=symbol,
                name=symbol,  # For US stocks, name is same as symbol
                sec_type="STK",
                exchange="SMART",
                currency="USD",
            )

            # 转换时间周期
            tf = resolve_timeframe(timeframe)
            if tf is None:
                logger.error(f"Invalid timeframe: {timeframe}")
                return []

            # 获取历史数据
            contract = self._client.make_contract(symbol_config)
            bars = self._client.get_historical_bars(
                contract=contract,
                timeframe=tf,
            )

            # 转换为字典格式
            result: List[Dict[str, Any]] = []
            for bar in bars:
                result.append(self.format_kline(
                    timestamp=bar.timestamp,
                    open_price=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                ))

            # 应用过滤和限制
            result = self.filter_and_limit(result, limit, before_time)

            # 记录日志
            self.log_result(symbol, result, timeframe)

            return result

        except Exception as e:
            logger.exception(f"Failed to get kline for {symbol}")
            return []

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时报价

        Args:
            symbol: 股票代码

        Returns:
            报价数据字典
        """
        if not self.is_connected():
            if not self.connect():
                logger.error("Failed to connect to IBKR Gateway")
                return {}

        try:
            if not self.is_connected():
                self.connect()

            # 创建合约配置
            symbol_config = SymbolConfig(
                symbol=symbol,
                name=symbol,  # For US stocks, name is same as symbol
                sec_type="STK",
                exchange="SMART",
                currency="USD",
            )

            contract = self._client.make_contract(symbol_config)
            qualified = self._client.qualify_contract(contract)

            # 使用 reqMktData 获取实时数据
            # 这里返回简化版 ticker 数据
            return {
                "symbol": symbol,
                "conId": qualified,
                "last": None,  # 需要通过市场数据回调获取
                "bid": None,
                "ask": None,
            }

        except Exception as e:
            logger.exception(f"Failed to get ticker for {symbol}")
            return {}
