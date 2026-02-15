"""
K线数据服务：优先从历史库读，缺则从网络拉取并回写数据库。
"""
import time
from typing import Dict, List, Any, Optional

from app.data_sources import DataSourceFactory
from app.data_sources.base import TIMEFRAME_SECONDS
from app.utils.cache import CacheManager
from app.utils.db import get_db_connection
from app.utils.logger import get_logger
from app.config import CacheConfig

logger = get_logger(__name__)


def _row_to_kline(row: Dict[str, Any]) -> Dict[str, Any]:
    """数据库行 -> 前端/接口 K 线格式 (time 为秒时间戳)"""
    return {
        'time': int(row['time_sec']),
        'open': float(row['open_price']),
        'high': float(row['high_price']),
        'low': float(row['low_price']),
        'close': float(row['close_price']),
        'volume': float(row['volume']),
    }


def _read_kline_range_from_db(
    market: str,
    symbol: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
) -> List[Dict[str, Any]]:
    """从库中读取 [start_ts, end_ts] 时间范围内的 K 线（含首尾）。"""
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """SELECT time_sec, open_price, high_price, low_price, close_price, volume
                   FROM qd_kline_cache
                   WHERE market = ? AND symbol = ? AND timeframe = ?
                   AND time_sec >= ? AND time_sec <= ?
                   ORDER BY time_sec ASC""",
                (market, symbol, timeframe, start_ts, end_ts),
            )
            rows = cur.fetchall()
            cur.close()
        return [_row_to_kline(r) for r in rows]
    except Exception as e:
        logger.debug(f"Kline DB range read skipped: {e}")
        return []


def _read_kline_from_db(
    market: str,
    symbol: str,
    timeframe: str,
    limit: int,
    before_time: Optional[int] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    从 qd_kline_cache 读取。before_time 为 None 时取最新 limit 条并校验是否足够新。
    失败或表不存在返回 None。
    """
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            if before_time is not None:
                cur.execute(
                    """SELECT time_sec, open_price, high_price, low_price, close_price, volume
                       FROM qd_kline_cache
                       WHERE market = ? AND symbol = ? AND timeframe = ?
                       AND time_sec < ?
                       ORDER BY time_sec DESC LIMIT ?""",
                    (market, symbol, timeframe, before_time, limit),
                )
            else:
                cur.execute(
                    """SELECT time_sec, open_price, high_price, low_price, close_price, volume
                       FROM qd_kline_cache
                       WHERE market = ? AND symbol = ? AND timeframe = ?
                       ORDER BY time_sec DESC LIMIT ?""",
                    (market, symbol, timeframe, limit),
                )
            rows = cur.fetchall()
            cur.close()
        if not rows:
            return None
        klines = [_row_to_kline(r) for r in rows]
        klines.sort(key=lambda x: x['time'])
        if before_time is not None:
            return klines
        interval = TIMEFRAME_SECONDS.get(timeframe, 86400)
        now_sec = int(time.time())
        if klines and (now_sec - klines[-1]['time']) > interval * 2:
            return None
        return klines
    except Exception as e:
        logger.debug(f"Kline DB read skipped: {e}")
        return None


def _write_kline_to_db(
    market: str,
    symbol: str,
    timeframe: str,
    klines: List[Dict[str, Any]],
) -> None:
    """将 K 线列表写入 qd_kline_cache，冲突时覆盖。"""
    if not klines:
        return
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            for k in klines:
                t = k.get('time')
                if t is None:
                    continue
                cur.execute(
                    """INSERT INTO qd_kline_cache
                       (market, symbol, timeframe, time_sec, open_price, high_price, low_price, close_price, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (market, symbol, timeframe, time_sec)
                       DO UPDATE SET
                         open_price = EXCLUDED.open_price,
                         high_price = EXCLUDED.high_price,
                         low_price = EXCLUDED.low_price,
                         close_price = EXCLUDED.close_price,
                         volume = EXCLUDED.volume,
                         created_at = NOW()
                       RETURNING time_sec""",
                    (
                        market,
                        symbol,
                        timeframe,
                        int(t),
                        float(k.get('open', 0)),
                        float(k.get('high', 0)),
                        float(k.get('low', 0)),
                        float(k.get('close', 0)),
                        float(k.get('volume', 0)),
                    ),
                )
            db.commit()
            cur.close()
        logger.info("Kline DB write: %s %s %s count=%d", market, symbol, timeframe, len(klines))
    except Exception as e:
        logger.warning("Kline DB write failed: %s", e)


class KlineService:
    """K线数据服务：优先数据库历史缓存，缺则网络并回写。"""

    def __init__(self):
        self.cache = CacheManager()
        self.cache_ttl = CacheConfig.KLINE_CACHE_TTL

    def get_kline(
        self,
        market: str,
        symbol: str,
        timeframe: str,
        limit: int = 300,
        before_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取K线：先查库，缺的只向网络请求「缺失区间」并合并回写（数据补全），再配合短期内存缓存。
        """
        if not before_time:
            cache_key = f"kline:{market}:{symbol}:{timeframe}:{limit}"
            cached = self.cache.get(cache_key)
            if cached:
                logger.info("Kline from memory cache: %s %s %s count=%d", market, symbol, timeframe, len(cached))
                return cached

        interval_sec = TIMEFRAME_SECONDS.get(timeframe, 86400)
        now_sec = int(time.time())
        if before_time is not None:
            need_end_ts = before_time - interval_sec
            need_start_ts = before_time - limit * interval_sec
        else:
            need_end_ts = now_sec
            need_start_ts = now_sec - limit * interval_sec

        from_db = _read_kline_range_from_db(
            market, symbol, timeframe, need_start_ts, need_end_ts
        )
        if len(from_db) >= limit:
            merged = sorted(from_db, key=lambda x: x['time'])
            if before_time is not None:
                result = [b for b in merged if b['time'] < before_time][-limit:]
            else:
                result = merged[-limit:] if len(merged) > limit else merged
            if len(result) >= limit:
                logger.info("Kline from DB cache: %s %s %s count=%d", market, symbol, timeframe, len(result))
                if not before_time:
                    if result and (now_sec - result[-1]['time']) <= interval_sec * 2:
                        ttl = self.cache_ttl.get(timeframe, 300)
                        self.cache.set(cache_key, result, ttl)
                return result

        existing_times = {b['time'] for b in from_db}
        needed_times = [
            need_start_ts + i * interval_sec
            for i in range(limit)
            if need_start_ts + i * interval_sec <= need_end_ts
        ][:limit]
        missing_times = [t for t in needed_times if t not in existing_times]

        fetched: List[Dict[str, Any]] = []
        missing_sorted = sorted(missing_times)
        if existing_times:
            gap_before = [t for t in missing_sorted if t < min(existing_times)]
            gap_after = [t for t in missing_sorted if t > max(existing_times)]
        else:
            gap_before = []
            gap_after = []
            missing_sorted = []

        if existing_times and gap_before:
            fetch_limit = min(len(gap_before) + 20, limit * 2)
            part = DataSourceFactory.get_kline(
                market, symbol, timeframe, fetch_limit,
                before_time=min(existing_times),
            )
            if part:
                fetched.extend(part)
        if existing_times and gap_after:
            fetch_limit = min(len(gap_after) + 20, limit * 2)
            part = DataSourceFactory.get_kline(
                market, symbol, timeframe, fetch_limit,
                before_time=need_end_ts + interval_sec,
            )
            if part:
                fetched.extend(part)
        if not fetched:
            fetched = DataSourceFactory.get_kline(
                market, symbol, timeframe, limit, before_time=before_time
            )

        by_time = {b['time']: b for b in from_db}
        for b in fetched:
            if b['time'] not in by_time:
                by_time[b['time']] = b
        merged = sorted(by_time.values(), key=lambda x: x['time'])
        if before_time is not None:
            result = [b for b in merged if b['time'] < before_time][-limit:]
        else:
            result = merged[-limit:] if len(merged) > limit else merged

        if fetched:
            _write_kline_to_db(market, symbol, timeframe, fetched)
        if not before_time and result:
            ttl = self.cache_ttl.get(timeframe, 300)
            self.cache.set(cache_key, result, ttl)
        return result
    
    def get_latest_price(self, market: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取最新价格（使用1分钟K线，已弃用，建议使用 get_realtime_price）"""
        klines = self.get_kline(market, symbol, '1m', 1)
        if klines:
            return klines[-1]
        return None
    
    def get_realtime_price(self, market: str, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        获取实时价格（优先使用 ticker API，降级使用分钟 K 线）
        
        Args:
            market: 市场类型 (Crypto, USStock, AShare, HShare, Forex, Futures)
            symbol: 交易对/股票代码
            force_refresh: 是否强制刷新（跳过缓存）
            
        Returns:
            实时价格数据: {
                'price': 最新价格,
                'change': 涨跌额,
                'changePercent': 涨跌幅,
                'high': 最高价,
                'low': 最低价,
                'open': 开盘价,
                'previousClose': 昨收价,
                'source': 数据来源 ('ticker' 或 'kline')
            }
        """
        # 构建缓存键（短时间缓存，避免频繁请求）
        cache_key = f"realtime_price:{market}:{symbol}"
        
        # 如果不是强制刷新，尝试使用缓存
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        result = {
            'price': 0,
            'change': 0,
            'changePercent': 0,
            'high': 0,
            'low': 0,
            'open': 0,
            'previousClose': 0,
            'source': 'unknown'
        }
        
        # 优先尝试使用 ticker API 获取实时价格
        try:
            ticker = DataSourceFactory.get_ticker(market, symbol)
            if ticker and ticker.get('last', 0) > 0:
                result = {
                    'price': ticker.get('last', 0),
                    'change': ticker.get('change', 0),
                    'changePercent': ticker.get('changePercent', 0),
                    'high': ticker.get('high', 0),
                    'low': ticker.get('low', 0),
                    'open': ticker.get('open', 0),
                    'previousClose': ticker.get('previousClose', 0),
                    'source': 'ticker'
                }
                # 缓存 30 秒
                self.cache.set(cache_key, result, 30)
                return result
        except Exception as e:
            logger.debug(f"Ticker API failed for {market}:{symbol}, falling back to kline: {e}")
        
        # 降级：使用 1 分钟 K 线
        try:
            klines = self.get_kline(market, symbol, '1m', 2)
            if klines and len(klines) > 0:
                latest = klines[-1]
                prev_close = klines[-2]['close'] if len(klines) > 1 else latest.get('open', 0)
                current_price = latest.get('close', 0)
                
                change = round(current_price - prev_close, 4) if prev_close else 0
                change_pct = round(change / prev_close * 100, 2) if prev_close and prev_close > 0 else 0
                
                result = {
                    'price': current_price,
                    'change': change,
                    'changePercent': change_pct,
                    'high': latest.get('high', 0),
                    'low': latest.get('low', 0),
                    'open': latest.get('open', 0),
                    'previousClose': prev_close,
                    'source': 'kline_1m'
                }
                # 缓存 30 秒
                self.cache.set(cache_key, result, 30)
                return result
        except Exception as e:
            logger.debug(f"1m kline failed for {market}:{symbol}, trying daily: {e}")
        
        # 最后降级：使用日线数据（适用于非交易时间）
        try:
            klines = self.get_kline(market, symbol, '1D', 2)
            if klines and len(klines) > 0:
                latest = klines[-1]
                prev_close = klines[-2]['close'] if len(klines) > 1 else latest.get('open', 0)
                current_price = latest.get('close', 0)
                
                change = round(current_price - prev_close, 4) if prev_close else 0
                change_pct = round(change / prev_close * 100, 2) if prev_close and prev_close > 0 else 0
                
                result = {
                    'price': current_price,
                    'change': change,
                    'changePercent': change_pct,
                    'high': latest.get('high', 0),
                    'low': latest.get('low', 0),
                    'open': latest.get('open', 0),
                    'previousClose': prev_close,
                    'source': 'kline_1d'
                }
                # 日线数据缓存 5 分钟
                self.cache.set(cache_key, result, 300)
                return result
        except Exception as e:
            logger.error(f"All price sources failed for {market}:{symbol}: {e}")
        
        return result

