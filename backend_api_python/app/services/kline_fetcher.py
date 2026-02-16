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

# ---------------------------------------------------------------------------
# 市场容差：各市场最大合法无数据间隔（秒）
# 用于缓存范围命中判断：stored_min <= need_start + gap 且 stored_max >= need_end - gap
# ---------------------------------------------------------------------------
MAX_GAP: Dict[tuple, int] = {
    ("Crypto", 60): 300,
    ("Forex", 60): 3 * 86400,
    ("Futures", 60): 3 * 86400,
    ("USStock", 60): 18 * 3600,
    ("HShare", 60): 18 * 3600,
    ("AShare", 60): 19 * 3600,
    ("Crypto", 86400): 2 * 86400,
    ("Forex", 86400): 4 * 86400,
    ("Futures", 86400): 4 * 86400,
    ("USStock", 86400): 5 * 86400,
    ("HShare", 86400): 6 * 86400,
    ("AShare", 86400): 10 * 86400,
}


def _get_max_gap(market: str, interval_sec: int) -> int:
    gap = MAX_GAP.get((market, interval_sec))
    if gap is not None:
        return gap
    if interval_sec <= 300:
        return MAX_GAP.get((market, 60), 3 * 86400)
    if interval_sec >= 86400:
        return MAX_GAP.get((market, 86400), 10 * 86400)
    return MAX_GAP.get((market, 60), 3 * 86400)


# ---------------------------------------------------------------------------
# qd_kline_ranges: 记录已存储数据的实际 min/max 时间
# ---------------------------------------------------------------------------
_RANGE_TABLE_ENSURED = False


def _ensure_range_table() -> None:
    global _RANGE_TABLE_ENSURED
    if _RANGE_TABLE_ENSURED:
        return
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS qd_kline_ranges (
                    market VARCHAR(50) NOT NULL,
                    symbol VARCHAR(50) NOT NULL,
                    interval_sec INTEGER NOT NULL,
                    min_ts BIGINT NOT NULL,
                    max_ts BIGINT NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (market, symbol, interval_sec)
                )
            """)
            db.commit()
            cur.close()
        _RANGE_TABLE_ENSURED = True
    except Exception as e:
        logger.debug("Range table ensure skipped: %s", e)


def _get_range(market: str, symbol: str, interval_sec: int) -> Optional[tuple]:
    _ensure_range_table()
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT min_ts, max_ts FROM qd_kline_ranges WHERE market = ? AND symbol = ? AND interval_sec = ?",
                (market, symbol, interval_sec),
            )
            row = cur.fetchone()
            cur.close()
        if row and row.get("min_ts") is not None:
            return (int(row["min_ts"]), int(row["max_ts"]))
        return None
    except Exception as e:
        logger.debug("Range read skipped: %s", e)
        return None


def _update_range(market: str, symbol: str, interval_sec: int, data_min_ts: int, data_max_ts: int) -> None:
    _ensure_range_table()
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """INSERT INTO qd_kline_ranges (market, symbol, interval_sec, min_ts, max_ts, updated_at)
                   VALUES (?, ?, ?, ?, ?, NOW())
                   ON CONFLICT (market, symbol, interval_sec)
                   DO UPDATE SET
                     min_ts = LEAST(qd_kline_ranges.min_ts, EXCLUDED.min_ts),
                     max_ts = GREATEST(qd_kline_ranges.max_ts, EXCLUDED.max_ts),
                     updated_at = NOW()""",
                (market, symbol, interval_sec, int(data_min_ts), int(data_max_ts)),
            )
            db.commit()
            cur.close()
    except Exception as e:
        logger.debug("Range update skipped: %s", e)


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
        _auto_update_range(market, symbol, klines, interval_sec)
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
                _auto_update_range(market, symbol, klines, interval_sec)
                return
            except Exception:
                pass
        logger.warning("Kline points write failed: %s", e)


def _auto_update_range(market: str, symbol: str, klines: List[Dict[str, Any]], interval_sec: int) -> None:
    ts_list = [int(k["time"]) for k in klines if k.get("time") is not None]
    if ts_list:
        _update_range(market, symbol, interval_sec, min(ts_list), max(ts_list))


# 分页拉取单页大小与轮间延时（防限流）
PAGINATE_CHUNK = 1000
PAGINATE_DELAY_SEC = 1.0
PAGINATE_MAX_ROUNDS = 15


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


def _fetch_1m_paginated(
    market: str,
    symbol: str,
    need_start_ts: int,
    need_end_ts: int,
    max_bars: int,
    delay_sec: float = PAGINATE_DELAY_SEC,
) -> tuple:
    """分页拉 1m（或回退 5m），每次最多 PAGINATE_CHUNK 根，轮间延时防限流。返回 (merged_klines, '1m'|'5m')。"""
    by_time: Dict[int, Dict] = {}
    next_before = need_end_ts + 60
    eff_tf = "1m"
    for r in range(PAGINATE_MAX_ROUNDS):
        chunk_limit = min(PAGINATE_CHUNK, max_bars - len(by_time))
        if chunk_limit <= 0:
            break
        fetched, eff_tf = _fetch_1m_or_fallback_5m(
            market, symbol, chunk_limit, before_time=next_before
        )
        if not fetched:
            break
        for b in fetched:
            by_time[b["time"]] = b
        min_ts = min(b["time"] for b in fetched)
        if min_ts <= need_start_ts:
            break
        next_before = min_ts
        if r < PAGINATE_MAX_ROUNDS - 1:
            time.sleep(delay_sec)
    merged = sorted(by_time.values(), key=lambda x: x["time"])
    return merged, eff_tf


def get_kline(
    market: str,
    symbol: str,
    timeframe: str,
    limit: int = 1000,
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
        # 1m: 0) 范围命中 1) 条数命中 2) 增量尾巴 3) fallback

        def _slice_1m(pts: List[Dict], lim: int, bt: Optional[int]) -> List[Dict]:
            pts = sorted(pts, key=lambda x: x['time'])
            if bt is not None:
                return [b for b in pts if b['time'] < bt][-lim:]
            return pts[-lim:] if len(pts) > lim else pts

        # 0) 范围命中检查
        stored_1m = _get_range(market, symbol, 60)
        gap_1m = _get_max_gap(market, 60)
        if stored_1m:
            sr_min, sr_max = stored_1m
            if sr_min <= need_start_ts + gap_1m and sr_max >= need_end_ts - gap_1m:
                from_points = _read_points_range_from_db(market, symbol, need_start_ts, need_end_ts, interval_sec=60)
                if from_points:
                    # 实时场景：范围命中但数据可能不够新，检查是否需要拉增量尾巴
                    if before_time is None and from_points:
                        max_ts_db = max(b['time'] for b in from_points)
                        if (now_sec - max_ts_db) > 600:
                            tail_limit = min((now_sec - max_ts_db) // interval_sec + 20, 2000)
                            fetched_tail, eff_tf = _fetch_1m_or_fallback_5m(
                                market, symbol, tail_limit, before_time=now_sec + interval_sec
                            )
                            if fetched_tail and eff_tf == "1m":
                                by_time = {b["time"]: b for b in from_points}
                                for b in fetched_tail:
                                    by_time[b["time"]] = b
                                merged = sorted(by_time.values(), key=lambda x: x["time"])
                                _write_points_to_db(market, symbol, fetched_tail, interval_sec=60)
                                logger.info("Kline range hit + tail: %s %s 1m count=%d", market, symbol, len(merged))
                                return _slice_1m(merged, limit, before_time)
                    result = _slice_1m(from_points, limit, before_time)
                    logger.info("Kline range hit 1m: %s %s count=%d", market, symbol, len(result))
                    return result
                return []

        # 1) 条数命中（兼容旧数据无 range 记录）
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

        # 2) 增量尾巴
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
                if fetch_limit > PAGINATE_CHUNK:
                    fetched_tail, eff_tf = _fetch_1m_paginated(
                        market, symbol, need_start_ts, need_end_ts, fetch_limit
                    )
                else:
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
                # 3) 拉网失败但有本地数据 -> fallback
                if from_db:
                    logger.warning("Kline 1m tail fetch failed, fallback to local: %s %s count=%d", market, symbol, len(from_db))
                    return _slice_1m(from_db, limit, before_time)
    else:
        # 非 1m：1) 范围命中 2) 同周期条数 3) 低层级换算 4) 拉网 5) fallback
        def _slice(merged: List[Dict], lim: int, before_ts: Optional[int]) -> List[Dict]:
            merged = sorted(merged, key=lambda x: x["time"])
            if before_ts is not None:
                return [b for b in merged if b["time"] < before_ts][-lim:]
            return merged[-lim:] if len(merged) > lim else merged

        # 1) 范围命中检查
        stored = _get_range(market, symbol, interval_sec)
        gap = _get_max_gap(market, interval_sec)
        if stored:
            sr_min, sr_max = stored
            if sr_min <= need_start_ts + gap and sr_max >= need_end_ts - gap:
                from_same = _read_points_range_from_db(
                    market, symbol, need_start_ts, need_end_ts, interval_sec=interval_sec
                )
                if from_same:
                    result = _slice(from_same, limit, before_time)
                    logger.info("Kline range hit: %s %s %s count=%d", market, symbol, timeframe, len(result))
                    return result
                return []

        # 2) 同周期条数（兼容旧数据尚无 range 记录的情况）
        from_same = _read_points_range_from_db(
            market, symbol, need_start_ts, need_end_ts, interval_sec=interval_sec
        )
        if len(from_same) >= limit:
            result = _slice(from_same, limit, before_time)
            logger.info("Kline from same layer: %s %s %s count=%d", market, symbol, timeframe, len(result))
            return result

        # 3) 低层级换算
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

        # 4) 拉网并缓存当前周期
        fetched: List[Dict[str, Any]] = []
        next_bt = need_end_ts + interval_sec
        request_limit = min(limit, PAGINATE_CHUNK)
        for _ in range(PAGINATE_MAX_ROUNDS):
            part = DataSourceFactory.get_kline(
                market, symbol, timeframe, request_limit, before_time=next_bt
            )
            if not part:
                break
            fetched.extend(part)
            if len(part) < request_limit:
                break
            min_ts = min(b["time"] for b in part)
            if min_ts <= need_start_ts:
                break
            next_bt = min_ts
            time.sleep(PAGINATE_DELAY_SEC)
        if fetched:
            _write_points_to_db(market, symbol, fetched, interval_sec=interval_sec)
            logger.info("Kline fetched and cached: %s %s %s count=%d", market, symbol, timeframe, len(fetched))
        by_time = {b["time"]: b for b in from_same}
        for b in (fetched or []):
            if b["time"] not in by_time:
                by_time[b["time"]] = b
        merged = sorted(by_time.values(), key=lambda x: x["time"])

        # 5) fallback: 拉网失败且无合并结果，返回库里已有数据
        if not merged:
            fallback = _read_points_range_from_db(market, symbol, need_start_ts, need_end_ts, interval_sec)
            if fallback:
                logger.warning("Network failed, fallback to local: %s %s %s count=%d", market, symbol, timeframe, len(fallback))
                return _slice(fallback, limit, before_time)
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
            if limit > PAGINATE_CHUNK:
                fetched, eff_tf = _fetch_1m_paginated(
                    market, symbol, need_start_ts, need_end_ts, limit
                )
            else:
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

    # fallback: 拉网失败但有本地数据
    if not result and from_db:
        logger.warning("Kline 1m gap-fill failed, fallback to local: %s %s count=%d", market, symbol, len(from_db))
        return _slice_1m(from_db, limit, before_time)
    return result
