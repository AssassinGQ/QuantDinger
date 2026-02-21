"""
宏观市场数据服务 — 为回测和活交易提供 VIX/DXY/Fear&Greed 历史及实时数据

缓存策略: DB 持久化 + 内存热缓存
  - 首次请求某日期范围 → 查 DB → 缺失日期从网络拉取 → 写回 DB → 返回
  - 后续请求 → 内存热缓存命中（TTL 默认 1 小时）
  - 进程重启 → 内存缓存丢失 → 从 DB 读取（毫秒级）→ 不再需要网络请求

数据注入到 df 后，指标代码可直接使用:
    df["vix"]         - VIX 恐慌指数（美股）
    df["vhsi"]        - VHSI 恒生波动率指数（港股）
    df["dxy"]         - 美元指数
    df["fear_greed"]  - Fear & Greed 指数 (0-100)
"""

import os
import time
import threading
from datetime import datetime, timedelta, date
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd

from app.utils.logger import get_logger

logger = get_logger(__name__)

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    logger.warning("yfinance not installed, VIX/DXY historical data unavailable. pip install yfinance")

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def _get_db():
    """延迟导入避免循环依赖"""
    from app.utils.db import get_db_connection
    return get_db_connection()


class MacroDataService:
    """获取并缓存 VIX / DXY / Fear&Greed 历史数据，合并到 K线 DataFrame"""

    _mem_cache: dict = {}
    _mem_lock = threading.Lock()
    _db_ready = False
    MEM_TTL = int(os.getenv("MACRO_CACHE_TTL", 3600))

    MACRO_COLUMNS = ["vix", "vhsi", "dxy", "fear_greed"]

    @classmethod
    def _ensure_table(cls):
        """首次使用时自动建表（和 kline_fetcher 同模式）"""
        if cls._db_ready:
            return
        try:
            with _get_db() as db:
                cur = db.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS qd_macro_data (
                        indicator VARCHAR(30) NOT NULL,
                        date_val DATE NOT NULL,
                        value DECIMAL(20,6) NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW(),
                        PRIMARY KEY (indicator, date_val)
                    )
                """)
                db.commit()
                cur.close()
            cls._db_ready = True
            logger.info("qd_macro_data table ensured")
        except Exception as e:
            logger.warning(f"Failed to ensure qd_macro_data table: {e}")

    # ── 公开接口 ──────────────────────────────────────────────────────

    @classmethod
    def enrich_dataframe(cls, df: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """向 OHLCV DataFrame 注入宏观数据列（回测用）"""
        if df.empty:
            return df

        macro_df = cls._get_macro_df(start_date, end_date)

        if macro_df is not None and not macro_df.empty:
            df_idx = df.index
            macro_idx = macro_df.index
            if hasattr(df_idx, 'tz') and df_idx.tz is not None and macro_idx.tz is None:
                macro_df.index = macro_df.index.tz_localize('UTC')
            elif hasattr(macro_idx, 'tz') and macro_idx.tz is not None and (not hasattr(df_idx, 'tz') or df_idx.tz is None):
                macro_df.index = macro_df.index.tz_localize(None)

            for col in cls.MACRO_COLUMNS:
                if col in macro_df.columns:
                    aligned = macro_df[col].reindex(df.index, method='ffill')
                    df[col] = aligned.values
                else:
                    df[col] = np.nan
        else:
            for col in cls.MACRO_COLUMNS:
                df[col] = np.nan

        return df

    @classmethod
    def enrich_dataframe_realtime(cls, df: pd.DataFrame) -> pd.DataFrame:
        """向 OHLCV DataFrame 注入宏观数据列（活交易用，最新 K 线用实时值覆盖）"""
        if df.empty:
            return df

        first_ts = df.index.min()
        last_ts = df.index.max()
        start = first_ts.tz_localize(None) if hasattr(first_ts, 'tz') and first_ts.tzinfo else first_ts
        end = last_ts.tz_localize(None) if hasattr(last_ts, 'tz') and last_ts.tzinfo else last_ts
        if isinstance(start, pd.Timestamp):
            start = start.to_pydatetime()
            end = end.to_pydatetime()

        df = cls.enrich_dataframe(df, start, end)

        realtime = cls._get_realtime_snapshot()
        if realtime:
            for col in cls.MACRO_COLUMNS:
                if col in realtime and col in df.columns:
                    df[col].iloc[-1] = realtime[col]

        return df

    # ── 核心: 先库后网 ──────────────────────────────────────────────

    @classmethod
    def _get_macro_df(cls, start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """获取合并后的宏观 DataFrame（内存热缓存 → DB → 网络）"""
        cache_key = f"macro_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"

        with cls._mem_lock:
            if cache_key in cls._mem_cache:
                cached_time, cached_df = cls._mem_cache[cache_key]
                if time.time() - cached_time < cls.MEM_TTL:
                    return cached_df

        sd = start_date - timedelta(days=10)
        ed = end_date + timedelta(days=1)

        dfs = []
        for indicator, fetcher in [
            ("vix", cls._fetch_vix_net),
            ("vhsi", cls._fetch_vhsi_net),
            ("dxy", cls._fetch_dxy_net),
            ("fear_greed", cls._fetch_fg_net),
        ]:
            series = cls._load_indicator(indicator, sd, ed, fetcher)
            if series is not None:
                dfs.append(series)

        if not dfs:
            return None

        result = dfs[0]
        for d in dfs[1:]:
            result = result.join(d, how='outer')
        result = result.sort_index().ffill()

        with cls._mem_lock:
            cls._mem_cache[cache_key] = (time.time(), result)

        return result

    @classmethod
    def _load_indicator(cls, indicator: str, start: datetime, end: datetime, net_fetcher) -> Optional[pd.DataFrame]:
        """单指标: DB查 → 缺失则网络拉 → 回写DB"""
        db_data = cls._read_db(indicator, start.date(), end.date())

        if db_data is not None and len(db_data) > 0:
            expected_days = (end.date() - start.date()).days
            coverage = len(db_data) / max(expected_days * 0.7, 1)
            if coverage > 0.8:
                return db_data

        net_data = net_fetcher(start, end)
        if net_data is not None and not net_data.empty:
            cls._write_db(indicator, net_data)
            return net_data

        return db_data if (db_data is not None and not db_data.empty) else None

    # ── DB 读写 ──────────────────────────────────────────────────────

    @classmethod
    def _read_db(cls, indicator: str, start_date: date, end_date: date) -> Optional[pd.DataFrame]:
        cls._ensure_table()
        try:
            with _get_db() as db:
                cur = db.cursor()
                cur.execute(
                    "SELECT date_val, value FROM qd_macro_data "
                    "WHERE indicator = ? AND date_val >= ? AND date_val <= ? "
                    "ORDER BY date_val",
                    (indicator, start_date.isoformat(), end_date.isoformat())
                )
                rows = cur.fetchall()
                cur.close()
            if not rows:
                return None
            records = [(pd.Timestamp(r['date_val']), float(r['value'])) for r in rows]
            df = pd.DataFrame(records, columns=['time', indicator]).set_index('time')
            return df
        except Exception as e:
            logger.debug(f"DB read for {indicator} failed (table may not exist yet): {e}")
            return None

    @classmethod
    def _write_db(cls, indicator: str, data: pd.DataFrame):
        """将网络拉取的数据回写 DB（UPSERT）"""
        if data.empty:
            return
        cls._ensure_table()
        col = data.columns[0] if len(data.columns) == 1 else indicator
        try:
            with _get_db() as db:
                cur = db.cursor()
                count = 0
                for ts, row in data.iterrows():
                    dt = ts.date() if hasattr(ts, 'date') else ts
                    val = float(row[col]) if col in row.index else float(row.iloc[0])
                    if pd.notna(val):
                        cur.execute(
                            "INSERT INTO qd_macro_data (indicator, date_val, value) "
                            "VALUES (?, ?, ?) "
                            "ON CONFLICT(indicator, date_val) DO UPDATE SET value=EXCLUDED.value "
                            "RETURNING date_val",
                            (indicator, dt.isoformat(), val)
                        )
                        count += 1
                db.commit()
                cur.close()
                logger.info(f"Wrote {count} rows for {indicator} to DB")
        except Exception as e:
            logger.warning(f"DB write for {indicator} failed: {e}")

    # ── 网络数据源 ───────────────────────────────────────────────────

    @classmethod
    def _fetch_vix_net(cls, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        if not HAS_YFINANCE:
            return None
        try:
            data = yf.download("^VIX", start=start.strftime('%Y-%m-%d'),
                               end=end.strftime('%Y-%m-%d'), progress=False, auto_adjust=True)
            if data.empty:
                return None
            close_col = data["Close"]
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]
            result = pd.DataFrame({"vix": close_col.values}, index=close_col.index)
            result.index = pd.to_datetime(result.index).tz_localize(None)
            result.index.name = "time"
            return result
        except Exception as e:
            logger.warning(f"VIX network fetch failed: {e}")
            return None

    @classmethod
    def _fetch_vhsi_net(cls, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        """VHSI 恒生波动率指数（港股，yfinance 格式 ^VHSI 或 ^1882.HK）"""
        if not HAS_YFINANCE:
            return None
        for ticker in ("^VHSI",):
            try:
                data = yf.download(ticker, start=start.strftime('%Y-%m-%d'),
                                  end=end.strftime('%Y-%m-%d'), progress=False, auto_adjust=True)
                if data.empty:
                    continue
                close_col = data["Close"]
                if isinstance(close_col, pd.DataFrame):
                    close_col = close_col.iloc[:, 0]
                result = pd.DataFrame({"vhsi": close_col.values}, index=close_col.index)
                result.index = pd.to_datetime(result.index).tz_localize(None)
                result.index.name = "time"
                return result
            except Exception as e:
                logger.debug(f"VHSI fetch ({ticker}) failed: {e}")
                continue
        return None

    @classmethod
    def _fetch_dxy_net(cls, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        if not HAS_YFINANCE:
            return None
        try:
            data = yf.download("DX-Y.NYB", start=start.strftime('%Y-%m-%d'),
                               end=end.strftime('%Y-%m-%d'), progress=False, auto_adjust=True)
            if data.empty:
                data = yf.download("UUP", start=start.strftime('%Y-%m-%d'),
                                   end=end.strftime('%Y-%m-%d'), progress=False, auto_adjust=True)
            if data.empty:
                return None
            close_col = data["Close"]
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]
            result = pd.DataFrame({"dxy": close_col.values}, index=close_col.index)
            result.index = pd.to_datetime(result.index).tz_localize(None)
            result.index.name = "time"
            return result
        except Exception as e:
            logger.warning(f"DXY network fetch failed: {e}")
            return None

    @classmethod
    def _fetch_fg_net(cls, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        if not HAS_REQUESTS:
            return None
        try:
            days = (end - start).days + 30
            url = f"https://api.alternative.me/fng/?limit={days}&format=json"
            resp = _requests.get(url, timeout=15)
            items = resp.json().get("data", [])
            if not items:
                return None
            records = []
            for item in items:
                ts = int(item["timestamp"])
                val = int(item["value"])
                dt = datetime.utcfromtimestamp(ts)
                records.append({"time": dt, "fear_greed": val})
            result = pd.DataFrame(records).set_index("time").sort_index()
            return result
        except Exception as e:
            logger.warning(f"Fear & Greed network fetch failed: {e}")
            return None

    # ── 实时快照 ─────────────────────────────────────────────────────

    @classmethod
    def _get_realtime_snapshot(cls) -> Optional[dict]:
        cache_key = "_realtime"
        with cls._mem_lock:
            if cache_key in cls._mem_cache:
                cached_time, cached_data = cls._mem_cache[cache_key]
                if time.time() - cached_time < 300:
                    return cached_data

        snapshot = {}
        if HAS_YFINANCE:
            try:
                vix_t = yf.Ticker("^VIX")
                info = vix_t.fast_info
                snapshot["vix"] = float(getattr(info, 'last_price', 0) or 0)
            except Exception:
                pass
            for vhsi_ticker in ("^VHSI",):
                try:
                    vhsi_t = yf.Ticker(vhsi_ticker)
                    info = vhsi_t.fast_info
                    val = float(getattr(info, 'last_price', 0) or 0)
                    if val > 0:
                        snapshot["vhsi"] = val
                        break
                except Exception:
                    continue
            try:
                dxy_t = yf.Ticker("DX-Y.NYB")
                info = dxy_t.fast_info
                snapshot["dxy"] = float(getattr(info, 'last_price', 0) or 0)
            except Exception:
                pass

        if HAS_REQUESTS:
            try:
                resp = _requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
                data = resp.json().get("data", [])
                if data:
                    snapshot["fear_greed"] = int(data[0]["value"])
            except Exception:
                pass

        with cls._mem_lock:
            cls._mem_cache[cache_key] = (time.time(), snapshot)

        return snapshot if snapshot else None

    @classmethod
    def clear_cache(cls):
        with cls._mem_lock:
            cls._mem_cache.clear()
