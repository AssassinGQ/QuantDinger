"""Cross-sectional strategy runner with Phase 21 execution semantics."""

from __future__ import annotations

import os
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.services.nq100_sources import resolve_shifted_execution_date
from app.strategies.base import IStrategyLoop
from app.strategies.runners.cross_sectional_filter_chain import (
    CashMnaForcedExitFilter,
    DelistingPolicyFilter,
    ExecutionPriceFilter,
    FilterAction,
    FilterChain,
    FilterContext,
    LiquidityVolumeFilter,
    MissingMarketRowPassThroughFilter,
    TradabilityFilter,
)
from app.utils import db
from app.strategies.runners.base_runner import BaseStrategyRunner
from app.utils.console import console_print
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExecutionPolicy:
    fallback_mode: str = "strict"
    min_liquidity_usd: float = 1_000_000.0
    long_halt_days: int = 5

    @classmethod
    def from_config(cls, trading_config: Dict[str, Any]) -> "ExecutionPolicy":
        return cls(
            fallback_mode=str(trading_config.get("fallback_mode", "strict")).lower(),
            min_liquidity_usd=float(
                os.getenv("CROSS_MIN_LIQUIDITY_USD", trading_config.get("min_liquidity_usd", 1_000_000.0))
            ),
            long_halt_days=int(os.getenv("CROSS_LONG_HALT_DAYS", trading_config.get("long_halt_days", 5))),
        )


def _to_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(float(value)).date()
    raise ValueError(f"Unsupported date value: {value!r}")


class CrossSectionalRunner(BaseStrategyRunner):
    """截面策略的运行流水线"""

    def _query_change_events(self, effective_dates: List[date]) -> Dict[str, List[Dict]]:
        """Query qd_nq100_change_events for remove events.

        D-08: Builds a dict of change events for universe symbols.
        Used by DelistingPolicyFilter to determine forced sell timing.

        Args:
            effective_dates: List of IC effective dates (unused in query, but kept for API consistency).

        Returns:
            Dict mapping symbol to list of events:
            {symbol: [{"event_type": "remove", "effective_date": date}]}
        """
        if not effective_dates:
            return {}
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT symbol, event_type, effective_date
                FROM qd_nq100_change_events
                WHERE event_type = 'remove'
                """,
            )
            rows = cursor.fetchall()
        # Build dict: {symbol: [{"event_type": "remove", "effective_date": date}]}
        events_by_symbol: Dict[str, List[Dict]] = {}
        for row in rows:
            sym = str(row[0]).upper()
            events_by_symbol.setdefault(sym, []).append({
                "event_type": str(row[1]),
                "effective_date": row[2],
            })
        return events_by_symbol

    def _get_tick_interval(self, strategy: Dict[str, Any]) -> int:
        """返回 tick 间隔（秒），子类可覆盖。"""
        trading_config = strategy.get("trading_config") or {}
        interval = int(trading_config.get("decide_interval", 300))
        return max(interval, 1)

    def run(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        exchange: Any,
    ) -> None:
        tick_interval_sec = self._get_tick_interval(strategy)
        last_tick_time = 0.0

        while True:
            try:
                if not self.is_running(strategy_id):
                    logger.info("Cross-sectional strategy %s stopped", strategy_id)
                    break
                should_continue, current_time, last_tick_time = self._wait_for_next_tick(
                    last_tick_time, tick_interval_sec
                )
                if should_continue:
                    continue

                keep_running = self._run_single_tick(
                    strategy_id, strategy, strat_instance, current_time, exchange
                )
                if not keep_running:
                    break

            except Exception as e:
                logger.error("Cross-sectional strategy %s loop error: %s", strategy_id, e)
                logger.error(traceback.format_exc())
                console_print(f"[strategy:{strategy_id}] loop error: {e}")
                time.sleep(5)

        logger.info("Cross-sectional strategy %s loop exited", strategy_id)

    def _build_context(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        current_time: float,
    ):
        """构建上下文，返回 None 表示跳过本次 tick。

        D-09: Pass excluded_from_universe from status_info to trading_config
        for Strategy-layer ranking pool adjustment.
        """
        last_rebalance = self.data_handler.get_last_rebalance_at(strategy_id)
        if not strat_instance.should_execute(strategy_id, strategy, last_rebalance):
            return None

        # D-09: Fetch status_info and pass excluded_from_universe to trading_config
        status_info = self.data_handler.get_strategy_status_info(strategy_id) or {}
        trading_config = strategy.get("trading_config") or {}
        trading_config["_excluded_from_universe"] = status_info.get("excluded_from_universe", [])
        strategy["trading_config"] = trading_config

        # Also pass existing positions for hold_until_signal_exit ranking pool adjustment
        positions = self.data_handler.get_all_positions(strategy_id) or []
        trading_config["_existing_positions"] = positions

        request = strat_instance.get_data_request(strategy_id, strategy, current_time)
        ctx = self.data_handler.get_input_context_cross(strategy_id, request)
        if ctx is None:
            logger.warning(
                "Strategy %s failed to get cross input context", strategy_id
            )
            return None

        ctx["strategy_id"] = strategy_id
        ctx["indicator_code"] = strategy.get("_indicator_code", "")
        ctx["symbol_indicator_codes"] = strategy.get("_symbol_indicator_codes", {})
        ctx["current_time"] = current_time
        return ctx

    def _dispatch_signals(
        self,
        strategy_id,
        strategy,
        signals,
        update_rebalance,
        metadata,
        exchange: Any,
    ):
        """执行信号、更新 rebalance 时间戳和 status_info。

        metadata 保存不受信号执行失败影响。

        D-09: For hold_until_signal_exit mode, update excluded_from_universe
        list after sell signals for excluded stocks are executed.
        """
        trading_config = strategy.get("trading_config") or {}
        policy = ExecutionPolicy.from_config(trading_config)
        filtered_signals, execution_meta = self._filter_phase21_signals(
            signals, policy, metadata or {}
        )
        merged_meta = {**(metadata or {}), **execution_meta}
        if merged_meta:
            self.data_handler.update_strategy_status_info(strategy_id, merged_meta)
        if update_rebalance:
            self.data_handler.update_last_rebalance(strategy_id)
        if filtered_signals:
            try:
                positions = self.data_handler.get_all_positions(strategy_id)
                logger.debug(
                    "Strategy %s dispatching %d signals, positions=%d",
                    strategy_id, len(filtered_signals), len(positions),
                )
                self.signal_executor.execute_batch(
                    strategy_ctx=strategy,
                    signals=filtered_signals,
                    all_positions=positions,
                    current_time=int(self._last_current_time),
                    exchange=exchange,
                )
            except Exception as exc:
                logger.error(
                    "Strategy %s signal execution failed: %s", strategy_id, exc,
                    exc_info=True,
                )

        # D-09: Update excluded_from_universe for hold_until_signal_exit mode
        delisting_policy = trading_config.get("delisting_policy", {"mode": "immediate"})
        mode = delisting_policy.get("mode", "immediate")

        if mode == "hold_until_signal_exit" and filtered_signals:
            # Collect symbols that have excluded_from_universe=True and are sell signals
            excluded_to_add = []
            for signal in filtered_signals:
                sym = signal.get("symbol", "").upper()
                # Check if it's a sell signal (close_* or forced_sell)
                signal_type = signal.get("type", "")
                is_sell = signal_type.startswith("close_") or signal_type == "forced_sell"
                is_excluded = signal.get("excluded_from_universe", False)
                if is_sell and is_excluded:
                    excluded_to_add.append(sym)

            if excluded_to_add:
                # Update strategy status_info with new excluded symbols
                existing_status = self.data_handler.get_strategy_status_info(strategy_id) or {}
                existing_excluded = existing_status.get("excluded_from_universe", [])
                new_excluded = list(set(existing_excluded + excluded_to_add))
                # Update status_info with the new excluded list
                self.data_handler.update_strategy_status_info(
                    strategy_id,
                    {"excluded_from_universe": new_excluded}
                )
                logger.debug(
                    "Strategy %s excluded_from_universe updated: %s -> %s",
                    strategy_id, existing_excluded, new_excluded,
                )

    def _filter_phase21_signals(
        self,
        signals: List[Dict[str, Any]],
        policy: ExecutionPolicy,
        metadata: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Apply no-lookahead and tradability semantics before dispatching.

        D-08/D-19/D-20: Integrates DelistingPolicyFilter for handling NQ100
        index reconstitution events with configurable forced sell timing.
        """
        effective_dates = {_to_date(d) for d in metadata.get("ic_effective_dates", [])}
        market_rows = metadata.get("market_rows", {})
        tradability = metadata.get("tradability", {})
        cash_mna_events = metadata.get("cash_mna", {})

        # D-08: Query change events for DelistingPolicyFilter
        trading_config = metadata.get("trading_config", {})
        change_events = self._query_change_events(list(effective_dates)) if effective_dates else {}

        # D-08/D-19: Extract delisting-related config for signals
        force_exit_symbols = trading_config.get("force_exit_symbols", [])
        delisting_policy = trading_config.get("delisting_policy", {"mode": "immediate"})
        execution_mode = metadata.get("execution_mode", "live")

        if not (effective_dates or market_rows or tradability or cash_mna_events):
            return signals, {
                "execution_logs": [],
                "fallback_count_total": 0,
                "fallback_rate": 0.0,
            }

        execution_logs: List[Dict[str, Any]] = []
        fallback_count = 0
        accepted: List[Dict[str, Any]] = []

        # D-08: DelistingPolicyFilter after CashMnaForcedExitFilter, before TradabilityFilter
        chain = FilterChain(
            [
                CashMnaForcedExitFilter(),
                DelistingPolicyFilter(),  # NEW: D-08 STRAT-02
                TradabilityFilter(),
                MissingMarketRowPassThroughFilter(),
                LiquidityVolumeFilter(),
                ExecutionPriceFilter(),
            ]
        )

        for signal in signals:
            # D-08/D-19: Add delisting-related metadata to each signal for DelistingPolicyFilter
            signal["delisting_policy"] = delisting_policy
            signal["force_exit_symbols"] = force_exit_symbols
            signal["execution_mode"] = execution_mode

            signal_date = _to_date(signal.get("signal_date", date.today()))
            execution_date = _to_date(
                signal.get("execution_date", signal_date + timedelta(days=1))
            )
            execution_date = resolve_shifted_execution_date(
                signal_date, execution_date, effective_dates
            )
            if execution_date <= signal_date:
                raise ValueError("execution_date must be greater than signal_date")

            symbol = str(signal.get("symbol", ""))
            market_row = market_rows.get(symbol, {})
            side = "buy" if str(signal.get("type", "")).startswith("open_") else "sell"
            context = FilterContext(
                signal=signal,
                symbol=symbol,
                side=side,
                signal_date_iso=signal_date.isoformat(),
                execution_date_iso=execution_date.isoformat(),
                market_row=market_row,
                tradability=tradability,
                cash_mna_events=cash_mna_events,
                min_liquidity_usd=policy.min_liquidity_usd,
                fallback_mode=policy.fallback_mode,
            )
            outcome = chain.run(context)
            if outcome.log_status:
                execution_logs.append(
                    {
                        "symbol": symbol,
                        "status": outcome.log_status,
                        "signal_date": signal_date.isoformat(),
                        "execution_date": execution_date.isoformat(),
                    }
                )
            if outcome.action == FilterAction.REJECT:
                continue
            if outcome.fallback_hit:
                fallback_count += 1
            accepted.append(outcome.signal or signal)

        fallback_rate = (fallback_count / len(accepted)) if accepted else 0.0
        return accepted, {
            "execution_logs": execution_logs,
            "fallback_count_total": fallback_count,
            "fallback_rate": round(fallback_rate, 6),
        }

    def _run_single_tick(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        current_time: float,
        exchange: Any,
    ) -> bool:
        """截面策略的 tick 逻辑：受 rebalance 周期控制。"""
        self._last_current_time = current_time
        ctx = self._build_context(
            strategy_id, strategy, strat_instance, current_time
        )
        if ctx is None:
            return True

        signals, keep_running, update_rebalance, metadata = strat_instance.get_signals(ctx)
        if not keep_running:
            return False

        self._dispatch_signals(
            strategy_id, strategy, signals, update_rebalance, metadata, exchange
        )
        return True