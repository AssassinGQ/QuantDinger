"""
数据处理器：集中 K 线、持仓等数据的拉取与构造，以及所有数据库操作。

Executor 调用 DataHandler 获取 InputContext、执行 DB 读写。
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from app.strategies.base import DataRequest, InputContext
from app.services.kline import KlineService
from app.services.macro_data_service import MacroDataService
from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DataHandler:
    """集中数据拉取与 InputContext 构造"""

    def __init__(self, kline_service: Optional[KlineService] = None):
        self.kline_service = kline_service or KlineService()

    def get_input_context_single(
        self,
        strategy_id: int,
        request: DataRequest,
        current_price: Optional[float] = None,
    ) -> Optional[InputContext]:
        """
        拉单标 K 线、持仓，构建 InputContext。
        request 需包含 symbol, timeframe, trading_config, need_macro, refresh_klines, df_override, history_limit, market_category
        """
        symbol = request.get("symbol", "")
        timeframe = request.get("timeframe", "1H")
        trading_config = request.get("trading_config") or {}
        need_macro = bool(request.get("need_macro", False))
        df_override = request.get("df_override")
        history_limit = int(request.get("history_limit", 500))
        market_category = request.get("market_category", "Crypto")

        if df_override is not None and len(df_override) > 0:
            df = df_override.copy()
        else:
            klines = self._fetch_latest_kline(
                symbol, timeframe, limit=history_limit, market_category=market_category
            )
            if not klines or len(klines) < 2:
                return None
            df = self._klines_to_dataframe(klines)
            if len(df) == 0:
                return None
            if need_macro:
                try:
                    df = MacroDataService.enrich_dataframe_realtime(df)
                except Exception as e:
                    logger.warning("Macro injection failed (continuing): %s", e)
        if current_price is not None and len(df) > 0:
            df = self._update_dataframe_with_current_price(df, current_price, timeframe)

        current_pos_list = self._get_current_positions(strategy_id, symbol)
        initial_highest = 0.0
        initial_position = 0
        initial_avg_entry_price = 0.0
        initial_position_count = 0
        initial_last_add_price = 0.0
        if current_pos_list:
            pos = current_pos_list[0]
            initial_highest = float(pos.get("highest_price", 0) or 0)
            pos_side = pos.get("side", "long")
            initial_position = 1 if pos_side == "long" else -1
            initial_avg_entry_price = float(pos.get("entry_price", 0) or 0)
            initial_position_count = 1
            initial_last_add_price = initial_avg_entry_price

        return {
            "df": df,
            "positions": current_pos_list,
            "initial_highest_price": initial_highest,
            "initial_position": initial_position,
            "initial_avg_entry_price": initial_avg_entry_price,
            "initial_position_count": initial_position_count,
            "initial_last_add_price": initial_last_add_price,
            "symbol": symbol,
            "trading_config": trading_config,
        }

    def get_input_context_cross(
        self,
        strategy_id: int,
        request: DataRequest,
    ) -> Optional[InputContext]:
        """
        拉多标 K 线、持仓，构建 InputContext。
        request 需包含 symbol_list, timeframe, trading_config, need_macro, history_limit, market_category
        """
        symbol_list = request.get("symbol_list") or []
        timeframe = request.get("timeframe", "1H")
        trading_config = request.get("trading_config") or {}
        need_macro = bool(request.get("need_macro", False))
        history_limit = int(request.get("history_limit", 200))
        market_category = request.get("market_category", "Crypto")

        if not symbol_list:
            return None

        all_data: Dict[str, pd.DataFrame] = {}
        for symbol in symbol_list:
            try:
                klines = self._fetch_latest_kline(
                    symbol,
                    timeframe,
                    limit=history_limit,
                    market_category=market_category,
                )
                if klines and len(klines) >= 2:
                    df = self._klines_to_dataframe(klines)
                    if need_macro:
                        try:
                            df = MacroDataService.enrich_dataframe_realtime(df)
                        except Exception as e:
                            logger.warning("Macro enrich failed for %s: %s", symbol, e)
                    if len(df) > 0:
                        all_data[symbol] = df
            except Exception as e:
                logger.warning("Failed to fetch data for %s: %s", symbol, e)
                continue
        if not all_data:
            return None
        positions = self._get_all_positions(strategy_id)
        return {
            "data": all_data,
            "positions": positions,
            "trading_config": trading_config,
        }

    def ensure_db_columns(self) -> None:
        """确保 qd_strategy_positions 表存在 highest_price、lowest_price 列"""
        try:
            db_type = os.getenv("DB_TYPE", "sqlite").lower()
            with get_db_connection() as db:
                cursor = db.cursor()
                col_names: set = set()
                if db_type == "postgresql":
                    try:
                        cursor.execute("""
                            SELECT column_name FROM information_schema.columns
                            WHERE table_name = 'qd_strategy_positions'
                        """)
                        cols = cursor.fetchall() or []
                        col_names = {
                            c.get("column_name") or c.get("COLUMN_NAME")
                            for c in cols
                            if isinstance(c, dict)
                        }
                    except Exception as e:
                        logger.warning("Failed to read PostgreSQL column schema: %s", e)
                        col_names = set()
                else:
                    try:
                        cursor.execute("PRAGMA table_info(qd_strategy_positions)")
                        cols = cursor.fetchall() or []
                        col_names = {c.get("name") for c in cols if isinstance(c, dict)}
                    except Exception as e:
                        logger.warning("Failed to read SQLite column schema: %s", e)
                        col_names = set()

                if "highest_price" not in col_names:
                    logger.info("Adding highest_price column to qd_strategy_positions (%s)...", db_type)
                    if db_type == "postgresql":
                        cursor.execute(
                            "ALTER TABLE qd_strategy_positions ADD COLUMN IF NOT EXISTS "
                            "highest_price DOUBLE PRECISION DEFAULT 0"
                        )
                    else:
                        cursor.execute("ALTER TABLE qd_strategy_positions ADD COLUMN highest_price REAL DEFAULT 0")
                    db.commit()
                if "lowest_price" not in col_names:
                    logger.info("Adding lowest_price column to qd_strategy_positions (%s)...", db_type)
                    if db_type == "postgresql":
                        cursor.execute(
                            "ALTER TABLE qd_strategy_positions ADD COLUMN IF NOT EXISTS "
                            "lowest_price DOUBLE PRECISION DEFAULT 0"
                        )
                    else:
                        cursor.execute("ALTER TABLE qd_strategy_positions ADD COLUMN lowest_price REAL DEFAULT 0")
                    db.commit()
                cursor.close()
        except Exception as e:
            logger.error("Failed to check/ensure DB columns: %s", e)

    def update_strategy_status(self, strategy_id: int, status: str) -> None:
        """更新策略状态"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    "UPDATE qd_strategies_trading SET status = %s WHERE id = %s",
                    (status, strategy_id),
                )
                db.commit()
                cursor.close()
        except Exception as e:
            logger.error("Failed to update strategy status: %s", e)

    def get_strategy_row(self, strategy_id: int) -> Optional[Dict[str, Any]]:
        """从 qd_strategies_trading 获取策略原始行"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    """
                    SELECT
                        id, strategy_name, strategy_type, status,
                        initial_capital, leverage, decide_interval,
                        execution_mode, notification_config,
                        indicator_config, exchange_config, trading_config, ai_model_config,
                        market_category
                    FROM qd_strategies_trading
                    WHERE id = %s
                    """,
                    (strategy_id,),
                )
                row = cursor.fetchone()
                cursor.close()
                return row
        except Exception as e:
            logger.warning("Failed to get strategy row for %s: %s", strategy_id, e)
            return None

    def get_indicator_code(self, indicator_id: int) -> Optional[str]:
        """从 qd_indicator_codes 获取指标代码"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    "SELECT code FROM qd_indicator_codes WHERE id = %s",
                    (indicator_id,),
                )
                result = cursor.fetchone()
                cursor.close()
                return result["code"] if result else None
        except Exception as e:
            logger.warning("Failed to get indicator code for %s: %s", indicator_id, e)
            return None

    def get_strategy_status(self, strategy_id: int) -> Optional[str]:
        """获取策略状态"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute("SELECT status FROM qd_strategies_trading WHERE id = %s", (strategy_id,))
                result = cursor.fetchone()
                cursor.close()
                return result.get("status") if result else None
        except Exception as e:
            logger.warning("Failed to get strategy status for %s: %s", strategy_id, e)
            return None

    def get_user_id(self, strategy_id: int) -> int:
        """获取策略所属 user_id"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute("SELECT user_id FROM qd_strategies_trading WHERE id = %s", (strategy_id,))
                row = cursor.fetchone()
                cursor.close()
                return int((row or {}).get("user_id") or 1)
        except Exception as e:
            logger.warning("Failed to get user_id for strategy %s: %s", strategy_id, e)
            return 1

    def get_current_positions(self, strategy_id: int, symbol: str) -> List[Dict[str, Any]]:
        """获取当前持仓（支持 symbol 匹配）"""
        return self._get_current_positions(strategy_id, symbol)

    def get_all_positions(self, strategy_id: int) -> List[Dict[str, Any]]:
        """获取策略的所有持仓"""
        return self._get_all_positions(strategy_id)

    def persist_notification(
        self,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        title: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> None:
        """持久化通知到 qd_strategy_notifications"""
        try:
            if user_id is None:
                user_id = self.get_user_id(strategy_id)
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO qd_strategy_notifications
                    (user_id, strategy_id, symbol, signal_type, channels, title, message, payload_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        int(user_id),
                        int(strategy_id),
                        str(symbol or ""),
                        str(signal_type or ""),
                        "browser",
                        str(title or ""),
                        str(message or ""),
                        json.dumps(payload or {}, ensure_ascii=False),
                    ),
                )
                db.commit()
                cur.close()
        except Exception as e:
            logger.warning("persist_notification failed: %s", e)

    def record_trade(
        self,
        strategy_id: int,
        symbol: str,
        trade_type: str,
        price: float,
        amount: float,
        value: float,
        profit: Optional[float] = None,
        commission: Optional[float] = None,
    ) -> None:
        """记录交易到 qd_strategy_trades"""
        try:
            user_id = self.get_user_id(strategy_id)
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    """
                    INSERT INTO qd_strategy_trades
                    (user_id, strategy_id, symbol, type, price, amount, value, commission, profit, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        user_id,
                        strategy_id,
                        symbol,
                        trade_type,
                        price,
                        amount,
                        value,
                        commission or 0,
                        profit,
                    ),
                )
                db.commit()
                cursor.close()
        except Exception as e:
            logger.error("Failed to record trade: %s", e)

    def update_position(
        self,
        strategy_id: int,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        current_price: float,
        highest_price: float = 0.0,
        lowest_price: float = 0.0,
    ) -> None:
        """更新持仓"""
        try:
            user_id = self.get_user_id(strategy_id)
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    """
                    INSERT INTO qd_strategy_positions
                    (user_id, strategy_id, symbol, side, size, entry_price, current_price, highest_price, lowest_price, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT(strategy_id, symbol, side) DO UPDATE SET
                        size = excluded.size,
                        entry_price = excluded.entry_price,
                        current_price = excluded.current_price,
                        highest_price = CASE WHEN excluded.highest_price > 0 THEN excluded.highest_price ELSE qd_strategy_positions.highest_price END,
                        lowest_price = CASE WHEN excluded.lowest_price > 0 THEN excluded.lowest_price ELSE qd_strategy_positions.lowest_price END,
                        updated_at = NOW()
                    """,
                    (user_id, strategy_id, symbol, side, size, entry_price, current_price, highest_price, lowest_price),
                )
                db.commit()
                cursor.close()
        except Exception as e:
            logger.error("Failed to update position: %s", e)

    def close_position(self, strategy_id: int, symbol: str, side: str) -> None:
        """平仓：删除持仓记录"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    "DELETE FROM qd_strategy_positions WHERE strategy_id = %s AND symbol = %s AND side = %s",
                    (strategy_id, symbol, side),
                )
                db.commit()
                cursor.close()
        except Exception as e:
            logger.error("Failed to close position: %s", e)

    def update_positions_current_price(
        self, strategy_id: int, symbol: str, current_price: float
    ) -> None:
        """更新持仓的当前价格"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    "UPDATE qd_strategy_positions SET current_price = %s WHERE strategy_id = %s AND symbol = %s",
                    (current_price, strategy_id, symbol),
                )
                db.commit()
                cursor.close()
        except Exception:
            pass

    def update_last_rebalance(self, strategy_id: int) -> None:
        """更新上次调仓时间"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                try:
                    cursor.execute(
                        "UPDATE qd_strategies_trading SET last_rebalance_at = NOW() WHERE id = %s",
                        (strategy_id,),
                    )
                    db.commit()
                except Exception:
                    pass
                cursor.close()
        except Exception as e:
            logger.warning("Failed to update last_rebalance_at: %s", e)

    def find_recent_pending_order(
        self,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        signal_ts: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """查找最近的 pending_order 记录（用于去重）"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                if signal_ts:
                    cur.execute(
                        """
                        SELECT id, status, created_at FROM pending_orders
                        WHERE strategy_id = %s AND symbol = %s AND signal_type = %s AND signal_ts = %s
                        ORDER BY id DESC LIMIT 1
                        """,
                        (strategy_id, symbol, signal_type, signal_ts),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, status, created_at FROM pending_orders
                        WHERE strategy_id = %s AND symbol = %s AND signal_type = %s
                        ORDER BY id DESC LIMIT 1
                        """,
                        (strategy_id, symbol, signal_type),
                    )
                row = cur.fetchone()
                cur.close()
                return row
        except Exception:
            return None

    def insert_pending_order(
        self,
        user_id: int,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        signal_ts: int,
        market_type: str,
        order_type: str,
        amount: float,
        price: float,
        execution_mode: str,
        status: str,
        priority: int,
        attempts: int,
        max_attempts: int,
        payload_json: str,
    ) -> Optional[int]:
        """插入 pending_order，返回 id"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO pending_orders
                    (user_id, strategy_id, symbol, signal_type, signal_ts, market_type, order_type, amount, price,
                     execution_mode, status, priority, attempts, max_attempts, last_error, payload_json,
                     created_at, updated_at, processed_at, sent_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NULL, NULL)
                    """,
                    (
                        user_id,
                        strategy_id,
                        symbol,
                        signal_type,
                        signal_ts,
                        market_type,
                        order_type,
                        amount,
                        price,
                        execution_mode,
                        status,
                        priority,
                        attempts,
                        max_attempts,
                        "",
                        payload_json,
                    ),
                )
                pending_id = cur.lastrowid
                db.commit()
                cur.close()
                return int(pending_id) if pending_id is not None else None
        except Exception as e:
            logger.error("Failed to insert pending_order: %s", e)
            return None

    def get_last_rebalance_at(self, strategy_id: int) -> Optional[datetime]:
        """查询策略上次调仓时间，供 Executor 判断是否调仓日。无记录或异常时返回 None。"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    "SELECT last_rebalance_at FROM qd_strategies_trading WHERE id = %s",
                    (strategy_id,),
                )
                result = cursor.fetchone()
                if not result or not result.get("last_rebalance_at"):
                    return None
                val = result["last_rebalance_at"]
                if isinstance(val, datetime):
                    return val
                if isinstance(val, str):
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                return None
        except Exception as e:
            logger.error("Failed to get last_rebalance_at: %s", e)
            return None

    def _fetch_latest_kline(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        market_category: str = "Crypto",
    ) -> List[Dict[str, Any]]:
        """获取最新 K 线数据"""
        try:
            return self.kline_service.get_kline(
                market=market_category,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                before_time=int(time.time()),
            )
        except Exception as e:
            logger.error(
                "Failed to fetch K-lines for %s:%s: %s",
                market_category,
                symbol,
                e,
            )
            return []

    def _klines_to_dataframe(self, klines: List[Dict[str, Any]]) -> pd.DataFrame:
        """将 K 线数据转换为 DataFrame"""
        if not klines:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(klines)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.set_index("time")
        elif "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
            df = df.set_index("timestamp")
        required_columns = ["open", "high", "low", "close", "volume"]
        available_columns = [c for c in required_columns if c in df.columns]
        if not available_columns:
            logger.warning("K-lines are missing required columns")
            return pd.DataFrame(columns=required_columns)
        df = df[available_columns]
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        return df.dropna()

    def _update_dataframe_with_current_price(
        self, df: pd.DataFrame, current_price: float, timeframe: str
    ) -> pd.DataFrame:
        """使用当前价格更新 DataFrame 最后一根 K 线"""
        if df is None or len(df) == 0:
            return df
        try:
            from app.data_sources.base import TIMEFRAME_SECONDS

            last_time = df.index[-1]
            timeframe_key = str(timeframe).upper()
            if timeframe_key not in TIMEFRAME_SECONDS:
                timeframe_key = str(timeframe).lower()
            tf_seconds = TIMEFRAME_SECONDS.get(timeframe_key, 60)

            last_ts = float(last_time.timestamp())
            now_ts = float(time.time())
            current_period_start = int(now_ts // tf_seconds) * tf_seconds

            if abs(last_ts - current_period_start) < 2:
                df.iloc[-1, df.columns.get_loc("close")] = current_price
                df.iloc[-1, df.columns.get_loc("high")] = max(
                    df.iloc[-1]["high"], current_price
                )
                df.iloc[-1, df.columns.get_loc("low")] = min(
                    df.iloc[-1]["low"], current_price
                )
            elif current_period_start > last_ts:
                new_row = pd.DataFrame(
                    {
                        "open": [current_price],
                        "high": [current_price],
                        "low": [current_price],
                        "close": [current_price],
                        "volume": [0.0],
                    },
                    index=[pd.to_datetime(current_period_start, unit="s", utc=True)],
                )
                df = pd.concat([df, new_row])
            return df
        except Exception as e:
            logger.error("Failed to update realtime candle: %s", e)
            return df

    def _get_current_positions(
        self, strategy_id: int, symbol: str
    ) -> List[Dict[str, Any]]:
        """获取当前持仓（支持 symbol 规范化匹配）"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    """
                    SELECT id, symbol, side, size, entry_price, highest_price, lowest_price
                    FROM qd_strategy_positions
                    WHERE strategy_id = %s
                """,
                    (strategy_id,),
                )
                all_positions = cursor.fetchall() or []

                matched = []
                sym_upper = (symbol or "").strip().upper()
                for pos in all_positions:
                    p_symbol = (pos.get("symbol") or "").strip().upper()
                    if sym_upper in p_symbol or p_symbol in sym_upper:
                        matched.append(pos)
                return matched
        except Exception as e:
            logger.error("Failed to get current positions: %s", e)
            return []

    def _get_all_positions(self, strategy_id: int) -> List[Dict[str, Any]]:
        """获取策略的所有持仓"""
        try:
            with get_db_connection() as db:
                cursor = db.cursor()
                cursor.execute(
                    """
                    SELECT id, symbol, side, size, entry_price, current_price,
                           highest_price, lowest_price
                    FROM qd_strategy_positions
                    WHERE strategy_id = %s
                """,
                    (strategy_id,),
                )
                return cursor.fetchall() or []
        except Exception as e:
            logger.error("Failed to get all positions: %s", e)
            return []
