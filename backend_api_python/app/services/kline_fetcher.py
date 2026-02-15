"""
K线拉取唯一入口：分层存各周期（1m/5m/15m/30m/1H/4H/1D/1W）到 qd_kline_points。
优先同周期读库 -> 不足则用低层级数据换算 -> 仍不足则拉网并缓存当前周期。
"""
import time
from typing import Dict, List, Any, Optional

from app.data_sources import DataSourceFactory
from app.data_sources.base import TIMEFRAME_SECONDS
from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 各周期可用的低层级（用于换算），从粗到细
LOWER_LEVELS: Dict[str, List[str]] = {
    "1W": ["1D", "4H", "1H", "5m", "1m"],
    "1D": ["4H", "1H", "5m", "1m"],
    "4H": ["1H", "5m", "1m"],
    "1H": ["5m", "1m"],
    "30m": ["1H", "5m", "1m"],
    "15m": ["5m", "1m"],
    "5m": ["1m"],
    "1m": [],
}


def _row_to_kline(row: Dict[str, Any]) -> Dict[str, Any]:
    """数据库行 -> K 线格式 (time 为秒时间戳)。"""
    return {
        'time': int(row['time_sec']),
        'open': float(row['open_price']),
        'high': float(row['high_price']),
        'low': float(row['low_price']),
        'close': float(row['close_price']),
        'volume': float(row['volume']),
    }


def _aggregate_bars(
    bars_1m: List[Dict[str, Any]],
    interval_sec: int,
) -> List[Dict[str, Any]]:
    """1m 点聚合成指定周期：按 time//interval_sec 分组，OHLCV 标准规则。"""
    if not bars_1m or interval_sec <= 60:
        return bars_1m if (interval_sec <= 60) else []
    from collections import defaultdict
    buckets = defaultdict(list)
    for b in bars_1m:
        t = b['time']
        bucket = (t // interval_sec) * interval_sec
        buckets[bucket].append(b)
    out = []
    for bucket in sorted(buckets.keys()):
        group = sorted(buckets[bucket], key=lambda x: x['time'])
        o, h = group[0]['open'], max(x['high'] for x in group)
        l, c = min(x['low'] for x in group), group[-1]['close']
        v = sum(x['volume'] for x in group)
        out.append({'time': bucket, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})
    return out


def _read_points_range_from_db(
    market: str,
    symbol: str,
    start_ts: int,
    end_ts: int,
    interval_sec: int = 60,
) -> List[Dict[str, Any]]:
    """qd_kline_points 读取 [start_ts, end_ts]，interval_sec 60=1m, 300=5m。"""
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """SELECT time_sec, open_price, high_price, low_price, close_price, volume
                   FROM qd_kline_points
                   WHERE market = ? AND symbol = ? AND interval_sec = ?
                   AND time_sec >= ? AND time_sec <= ?
                   ORDER BY time_sec ASC""",
                (market, symbol, interval_sec, start_ts, end_ts),
            )
            rows = cur.fetchall()
            cur.close()
        return [_row_to_kline(r) for r in rows]
    except Exception as e:
        if interval_sec == 60:
            try:
                with get_db_connection() as db:
                    cur = db.cursor()
                    cur.execute(
                        """SELECT time_sec, open_price, high_price, low_price, close_price, volume
                           FROM qd_kline_points
                           WHERE market = ? AND symbol = ?
                           AND time_sec >= ? AND time_sec <= ?
                           ORDER BY time_sec ASC""",
                        (market, symbol, start_ts, end_ts),
                    )
                    rows = cur.fetchall()
                    cur.close()
                return [_row_to_kline(r) for r in rows]
            except Exception as e2:
                logger.debug("Points DB range read (legacy) skipped: %s", e2)
        else:
            logger.debug("Points DB range read skipped: %s", e)
        return []


def _read_points_range_prefer_1m_then_5m(
    market: str,
    symbol: str,
    start_ts: int,
    end_ts: int,
) -> List[Dict[str, Any]]:
    """优先 1m 点，无则 5m 点，供聚合 1H/4H/1D/1W。"""
    out = _read_points_range_from_db(market, symbol, start_ts, end_ts, interval_sec=60)
    if out:
        return out
    return _read_points_range_from_db(market, symbol, start_ts, end_ts, interval_sec=300)


def _read_points_max_time(market: str, symbol: str) -> Optional[int]:
    """qd_kline_points 该标的最大 time_sec（1m/5m 取最大）。"""
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT max(time_sec) AS max_ts FROM qd_kline_points WHERE market = ? AND symbol = ?",
                (market, symbol),
            )
            row = cur.fetchone()
            cur.close()
        if row and row.get("max_ts") is not None:
            return int(row["max_ts"])
        return None
    except Exception as e:
        logger.debug("Points max time read skipped: %s", e)
        return None


def _write_points_to_db(
    market: str,
    symbol: str,
    klines: List[Dict[str, Any]],
    interval_sec: int = 60,
) -> None:
    """写入 qd_kline_points，冲突覆盖。interval_sec 60=1m, 300=5m。"""
    if not klines:
        return
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            for k in klines:
                t = k.get("time")
                if t is None:
                    continue
                cur.execute(
                    """INSERT INTO qd_kline_points
                       (market, symbol, time_sec, interval_sec, open_price, high_price, low_price, close_price, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (market, symbol, time_sec, interval_sec)
                       DO UPDATE SET
                         open_price = EXCLUDED.open_price,
                         high_price = EXCLUDED.high_price,
                         low_price = EXCLUDED.low_price,
                         close_price = EXCLUDED.close_price,
                         volume = EXCLUDED.volume,
                         created_at = NOW()
                       RETURNING time_sec""",
                    (
                        market, symbol, int(t), interval_sec,
                        float(k.get("open", 0)), float(k.get("high", 0)),
                        float(k.get("low", 0)), float(k.get("close", 0)), float(k.get("volume", 0)),
                    ),
                )
            db.commit()
            cur.close()
        logger.info("Kline points write: %s %s interval_sec=%d count=%d", market, symbol, interval_sec, len(klines))
    except Exception as e:
        if interval_sec == 60:
            try:
                with get_db_connection() as db:
                    cur = db.cursor()
                    for k in klines:
                        t = k.get("time")
                        if t is None:
                            continue
                        cur.execute(
                            """INSERT INTO qd_kline_points
                               (market, symbol, time_sec, open_price, high_price, low_price, close_price, volume)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                               ON CONFLICT (market, symbol, time_sec)
                               DO UPDATE SET open_price=EXCLUDED.open_price, high_price=EXCLUDED.high_price,
                                 low_price=EXCLUDED.low_price, close_price=EXCLUDED.close_price,
                                 volume=EXCLUDED.volume, created_at=NOW()
                               RETURNING time_sec""",
                            (
                                market, symbol, int(t),
                                float(k.get("open", 0)), float(k.get("high", 0)),
                                float(k.get("low", 0)), float(k.get("close", 0)), float(k.get("volume", 0)),
                            ),
                        )
                    db.commit()
                    cur.close()
                logger.info("Kline points write (legacy): %s %s count=%d", market, symbol, len(klines))
                return
            except Exception:
                pass
        logger.warning("Kline points write failed: %s", e)


def _fetch_1m_or_fallback_5m(
    market: str,
    symbol: str,
    limit: int,
    before_time: Optional[int] = None,
) -> tuple:
    """拉网：先 1m，无则 5m。返回 (klines, '1m'|'5m')。"""
    data = DataSourceFactory.get_kline(market, symbol, "1m", limit, before_time=before_time)
    if data and len(data) >= min(10, limit):
        return data, "1m"
    data5 = DataSourceFactory.get_kline(
        market, symbol, "5m", limit=min(limit, 200), before_time=before_time
    )
    if data5:
        return data5, "5m"
    return (data or []), "1m"


def get_kline(
    market: str,
    symbol: str,
    timeframe: str,
    limit: int = 300,
    before_time: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    获取K线唯一入口。只存点：优先读库（1m点->5m点），不够则拉网写点，再按周期聚合返回前端K线格式。
    """
    interval_sec = TIMEFRAME_SECONDS.get(timeframe, 86400)
    now_sec = int(time.time())
    if before_time is not None:
        need_end_ts = before_time - interval_sec
        need_start_ts = before_time - limit * interval_sec
    else:
        need_end_ts = now_sec
        need_start_ts = now_sec - limit * interval_sec

    if timeframe == '1m':
        # 1m：优先 1m 点
        from_points = _read_points_range_from_db(market, symbol, need_start_ts, need_end_ts, interval_sec=60)
        if len(from_points) < limit and before_time is None:
            max_ts = _read_points_max_time(market, symbol)
            if max_ts is not None and max_ts < need_end_ts:
                tail_start = max_ts - (limit * interval_sec)
                from_points = _read_points_range_from_db(
                    market, symbol, tail_start, max_ts, interval_sec=60
                )
        if len(from_points) >= limit:
            merged = sorted(from_points, key=lambda x: x['time'])
            if before_time is not None:
                result = [b for b in merged if b['time'] < before_time][-limit:]
            else:
                result = merged[-limit:] if len(merged) > limit else merged
            last_bar_fresh = result and (now_sec - result[-1]['time']) <= interval_sec * 2
            if len(result) >= limit and (before_time is not None or last_bar_fresh):
                logger.info("Kline from points 1m: %s %s count=%d", market, symbol, len(result))
                return result
        from_db = from_points
        need_tail = (
            before_time is None
            and len(from_db) > 0
            and (len(from_db) < limit or (now_sec - max(b['time'] for b in from_db)) > 600)
        )
        if need_tail:
            max_ts_db = max(b['time'] for b in from_db)
            tail_bars = (need_end_ts - max_ts_db) // interval_sec
            if tail_bars > 0:
                fetch_limit = min(tail_bars + 20, max(limit * 2, 50000))
                fetched_tail, eff_tf = _fetch_1m_or_fallback_5m(
                    market, symbol, fetch_limit, before_time=need_end_ts + interval_sec
                )
                if fetched_tail:
                    if eff_tf == "1m":
                        by_time = {b["time"]: b for b in from_db}
                        for b in fetched_tail:
                            if b["time"] not in by_time:
                                by_time[b["time"]] = b
                        merged = sorted(by_time.values(), key=lambda x: x["time"])
                        result = merged[-limit:] if len(merged) > limit else merged
                        _write_points_to_db(market, symbol, merged, interval_sec=60)
                        logger.info("Kline points incremental: %s %s fetched=%d total=%d", market, symbol, len(fetched_tail), len(result))
                        return result
                    _write_points_to_db(market, symbol, fetched_tail, interval_sec=300)
                    result = fetched_tail[-limit:] if len(fetched_tail) > limit else fetched_tail
                    logger.info("Kline 1m fallback 5m: %s %s count=%d", market, symbol, len(result))
                    return result
    else:
        # 非 1m：1) 同周期 2) 低层级换算 3) 拉网并缓存当前周期
        def _slice(merged: List[Dict], lim: int, before_ts: Optional[int]) -> List[Dict]:
            merged = sorted(merged, key=lambda x: x["time"])
            if before_ts is not None:
                return [b for b in merged if b["time"] < before_ts][-lim:]
            return merged[-lim:] if len(merged) > lim else merged

        # 1) 同周期
        from_same = _read_points_range_from_db(
            market, symbol, need_start_ts, need_end_ts, interval_sec=interval_sec
        )
        if len(from_same) >= limit:
            result = _slice(from_same, limit, before_time)
            logger.info("Kline from same layer: %s %s %s count=%d", market, symbol, timeframe, len(result))
            return result

        # 2) 低层级换算
        for lower_tf in LOWER_LEVELS.get(timeframe, []):
            lower_sec = TIMEFRAME_SECONDS.get(lower_tf, 60)
            from_lower = _read_points_range_from_db(
                market, symbol, need_start_ts, need_end_ts, interval_sec=lower_sec
            )
            if not from_lower:
                continue
            agg = _aggregate_bars(from_lower, interval_sec)
            if len(agg) >= limit:
                result = _slice(agg, limit, before_time)
                logger.info("Kline from lower layer: %s %s %s from %s count=%d", market, symbol, timeframe, lower_tf, len(result))
                return result

        # 3) 拉网并缓存当前周期
        fetched = DataSourceFactory.get_kline(
            market, symbol, timeframe, limit, before_time=need_end_ts + interval_sec
        )
        if fetched:
            _write_points_to_db(market, symbol, fetched, interval_sec=interval_sec)
            logger.info("Kline fetched and cached: %s %s %s count=%d", market, symbol, timeframe, len(fetched))
        by_time = {b["time"]: b for b in from_same}
        for b in (fetched or []):
            if b["time"] not in by_time:
                by_time[b["time"]] = b
        merged = sorted(by_time.values(), key=lambda x: x["time"])
        return _slice(merged, limit, before_time)

    # 1m 拉网补缺或首次（仅 1m 会走到这里）
    from_db = from_points
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
        gap_before, gap_after = [], []

    if existing_times and gap_before:
        part = DataSourceFactory.get_kline(
            market, symbol, timeframe, min(len(gap_before) + 20, limit * 2),
            before_time=min(existing_times),
        )
        if part:
            fetched.extend(part)
    if existing_times and gap_after:
        part = DataSourceFactory.get_kline(
            market, symbol, timeframe, min(len(gap_after) + 20, limit * 2),
            before_time=need_end_ts + interval_sec,
        )
        if part:
            fetched.extend(part)
    eff_tf = timeframe
    if not fetched:
        fetch_before = before_time if before_time is not None else need_end_ts + interval_sec
        if timeframe == "1m":
            fetched, eff_tf = _fetch_1m_or_fallback_5m(market, symbol, limit, before_time=fetch_before)
        else:
            fetched = DataSourceFactory.get_kline(market, symbol, timeframe, limit, before_time=fetch_before)

    by_time = {b["time"]: b for b in from_db}
    for b in fetched:
        if b["time"] not in by_time:
            by_time[b["time"]] = b
    merged = sorted(by_time.values(), key=lambda x: x["time"])
    if before_time is not None:
        result = [b for b in merged if b["time"] < before_time][-limit:]
    else:
        result = merged[-limit:] if len(merged) > limit else merged

    if fetched:
        if eff_tf == "1m":
            _write_points_to_db(market, symbol, merged, interval_sec=60)
        else:
            _write_points_to_db(market, symbol, merged, interval_sec=300)
    return result
