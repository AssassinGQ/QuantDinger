"""Phase 21 cross-sectional execution filter chain.

Includes DelistingPolicyFilter (STRAT-02) for handling NQ100 index reconstitution
events with configurable forced sell timing.

Architecture (D-06):
- Strategy layer manages universe pool and ranking
- Runner layer (via filters) handles execution timing and forced sell triggers
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.utils import db


class FilterAction(str, Enum):
    CONTINUE = "continue"
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass
class FilterOutcome:
    action: FilterAction
    signal: Optional[Dict[str, Any]] = None
    log_status: Optional[str] = None
    fallback_hit: bool = False


@dataclass
class FilterContext:
    signal: Dict[str, Any]
    symbol: str
    side: str
    signal_date_iso: str
    execution_date_iso: str
    market_row: Dict[str, Any]
    tradability: Dict[str, Any]
    cash_mna_events: Dict[str, Any]
    min_liquidity_usd: float
    fallback_mode: str


def resolve_execution_price(row_t1: Dict[str, Any], mode: str) -> Tuple[Optional[float], str]:
    """Resolve execution price from next_open with optional fallbacks."""
    next_open = row_t1.get("next_open")
    if next_open is not None and not math.isnan(float(next_open)) and float(next_open) > 0:
        return float(next_open), "next_open"

    if mode == "strict":
        return None, "none"

    fallback_field = {"ffill": "open_ffill", "close": "close", "bfill": "open_bfill"}.get(mode)
    if not fallback_field:
        return None, "none"

    candidate = row_t1.get(fallback_field)
    if candidate is None or math.isnan(float(candidate)) or float(candidate) <= 0:
        return None, "none"
    return float(candidate), mode


class SignalFilter:
    def apply(self, ctx: FilterContext) -> FilterOutcome:
        raise NotImplementedError


class CashMnaForcedExitFilter(SignalFilter):
    def apply(self, ctx: FilterContext) -> FilterOutcome:
        if ctx.symbol not in ctx.cash_mna_events:
            return FilterOutcome(FilterAction.CONTINUE)
        forced = {
            **ctx.signal,
            "type": "forced_cash_exit",
            "execution_date": ctx.execution_date_iso,
        }
        return FilterOutcome(FilterAction.ACCEPT, signal=forced, log_status="forced_cash_exit")


class TradabilityFilter(SignalFilter):
    def apply(self, ctx: FilterContext) -> FilterOutcome:
        if str(ctx.tradability.get(ctx.symbol, "TRADABLE")).upper() != "UNTRADABLE":
            return FilterOutcome(FilterAction.CONTINUE)
        status = (
            "skipped_untradable_buy_cash_kept"
            if ctx.side == "buy"
            else "skipped_untradable_sell_hold_position"
        )
        return FilterOutcome(FilterAction.REJECT, log_status=status)


class MissingMarketRowPassThroughFilter(SignalFilter):
    def apply(self, ctx: FilterContext) -> FilterOutcome:
        if ctx.market_row:
            return FilterOutcome(FilterAction.CONTINUE)
        accepted = {
            **ctx.signal,
            "signal_date": ctx.signal_date_iso,
            "execution_date": ctx.execution_date_iso,
        }
        return FilterOutcome(FilterAction.ACCEPT, signal=accepted)


class LiquidityVolumeFilter(SignalFilter):
    def apply(self, ctx: FilterContext) -> FilterOutcome:
        liquidity = float(ctx.market_row.get("adv20_usd", ctx.min_liquidity_usd))
        if liquidity >= ctx.min_liquidity_usd:
            return FilterOutcome(FilterAction.CONTINUE)
        status = (
            "skipped_untradable_buy_cash_kept"
            if ctx.side == "buy"
            else "skipped_untradable_sell_hold_position"
        )
        return FilterOutcome(FilterAction.REJECT, log_status=status)


class ExecutionPriceFilter(SignalFilter):
    def apply(self, ctx: FilterContext) -> FilterOutcome:
        execution_price, source = resolve_execution_price(ctx.market_row, ctx.fallback_mode)
        if execution_price is None:
            status = (
                "skipped_untradable_buy_cash_kept"
                if ctx.side == "buy"
                else "skipped_untradable_sell_hold_position"
            )
            return FilterOutcome(FilterAction.REJECT, log_status=status)
        accepted = {
            **ctx.signal,
            "signal_date": ctx.signal_date_iso,
            "execution_date": ctx.execution_date_iso,
            "execution_price": execution_price,
            "price_source": source,
        }
        return FilterOutcome(
            FilterAction.ACCEPT,
            signal=accepted,
            fallback_hit=(source != "next_open"),
        )


class DelistingPolicyFilter(SignalFilter):
    """
    STRAT-02: Handle index reconstitution events with configurable forced sell timing.

    This filter processes symbols that have been removed from the NQ100 index,
    triggering forced sell based on the delisting_policy configuration:

    - immediate (D-12): Forced sell on/after effective_date
    - delayed (D-13): Forced sell after N months from effective_date
    - hold_until_signal_exit (D-09): No forced sell from filter; Strategy handles ranking

    Special cases (D-14/D-15/D-16):
    - force_exit_symbols: Manual marking for bankruptcy/fraud/delisting risk
      - Override all delisting_policy timing (D-14)
      - Backtest assumes total loss (execution_price=0.0) (D-15)
      - Live trading uses actual execution price from ExecutionPriceFilter (D-14)

    Architecture (D-06):
    - Strategy layer manages universe pool (removes excluded symbols from ranking)
    - Runner layer (this filter) handles execution timing for positions held

    Database query (D-08):
    - Reads from qd_nq100_change_events for event_type='remove'
    - Filters by effective_date <= execution_date (event must have occurred)
    """

    def apply(self, ctx: FilterContext) -> FilterOutcome:
        """Process delisting policy for the given context."""
        # D-14/D-16: force_exit_symbols override (highest priority)
        force_exit_symbols = ctx.signal.get("force_exit_symbols", [])
        # Normalize to set for O(1) lookup (case-insensitive)
        if isinstance(force_exit_symbols, list):
            force_exit_set = set(
                s.upper().strip() for s in force_exit_symbols
                if isinstance(s, str) and s.strip()
            )
        else:
            force_exit_set = set()

        # D-14: Immediate forced sell for special cases, bypass all delisting_policy timing
        if ctx.symbol.upper() in force_exit_set:
            forced = {
                **ctx.signal,
                "type": "forced_sell",
                "force_exit_reason": "manual_force_exit",
                "execution_date": ctx.execution_date_iso,
            }
            # D-15: Backtest total loss assumption for force_exit_symbols
            execution_mode = ctx.signal.get("execution_mode", "live")  # Default to live
            if execution_mode == "backtest":
                # D-15: Total loss assumption for bankruptcy/fraud cases
                forced["execution_price"] = 0.0
                forced["price_source"] = "total_loss_assumption"
                return FilterOutcome(
                    FilterAction.ACCEPT,
                    signal=forced,
                    log_status="forced_exit_override_backtest_total_loss",
                )
            # D-14: Live trading uses actual execution price (ExecutionPriceFilter handles)
            return FilterOutcome(
                FilterAction.ACCEPT,
                signal=forced,
                log_status="forced_exit_override",
            )

        # Extract delisting_policy from signal (D-08)
        delisting_policy = ctx.signal.get("delisting_policy", {})
        mode = delisting_policy.get("mode", "immediate")  # Default per D-12
        months = delisting_policy.get("months", 3)  # Default per D-11

        # Query qd_nq100_change_events for symbol's remove events (D-08)
        # effective_date <= execution_date means event has occurred
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT effective_date
                FROM qd_nq100_change_events
                WHERE symbol = %s AND event_type = 'remove' AND effective_date <= %s
                ORDER BY effective_date DESC LIMIT 1
                """,
                (ctx.symbol, ctx.execution_date_iso),
            )
            row = cursor.fetchone()

        # No remove event found - pass through (add events don't trigger forced sell)
        if not row:
            return FilterOutcome(FilterAction.CONTINUE)

        effective_date = row[0]
        exec_date = date.fromisoformat(ctx.execution_date_iso)

        # Handle different modes (D-12, D-13, D-09)
        if mode == "immediate":
            # D-12: Sell on/after effective_date
            if exec_date >= effective_date:
                forced = {
                    **ctx.signal,
                    "type": "forced_sell",
                    "delisting_event_date": effective_date.isoformat(),
                    "execution_date": ctx.execution_date_iso,
                }
                return FilterOutcome(
                    FilterAction.ACCEPT,
                    signal=forced,
                    log_status="forced_delisting_exit_immediate",
                )
            # Before effective_date, no action yet
            return FilterOutcome(FilterAction.CONTINUE)

        if mode == "delayed":
            # D-13: Sell after delay period (N months from effective_date)
            delayed_sell_date = self._calculate_delayed_date(effective_date, months)
            if exec_date >= delayed_sell_date:
                forced = {
                    **ctx.signal,
                    "type": "forced_sell",
                    "delisting_event_date": effective_date.isoformat(),
                    "delayed_months": months,
                    "execution_date": ctx.execution_date_iso,
                }
                return FilterOutcome(
                    FilterAction.ACCEPT,
                    signal=forced,
                    log_status="forced_delisting_exit_delayed",
                )
            # Within delay period, continue holding
            return FilterOutcome(FilterAction.CONTINUE)

        if mode == "hold_until_signal_exit":
            # D-09: Filter does NOT trigger forced sell
            # Strategy layer handles ranking pool (removed stock still in ranking)
            # Runner marks excluded_from_universe after sell signal (Plan 04)
            return FilterOutcome(FilterAction.CONTINUE)

        # Unknown mode - default to immediate behavior
        if exec_date >= effective_date:
            forced = {
                **ctx.signal,
                "type": "forced_sell",
                "delisting_event_date": effective_date.isoformat(),
                "execution_date": ctx.execution_date_iso,
            }
            return FilterOutcome(
                FilterAction.ACCEPT,
                signal=forced,
                log_status="forced_delisting_exit_immediate",
            )
        return FilterOutcome(FilterAction.CONTINUE)

    def _calculate_delayed_date(self, effective_date: date, months: int) -> date:
        """
        Calculate delayed sell date: effective_date + N months.

        Handles month boundaries:
        - Jan 31 + 1 month = Feb 28/29 (leap year)
        - Mar 31 + 1 month = Apr 30

        Args:
            effective_date: The index removal effective date
            months: Number of months to delay

        Returns:
            The delayed sell date
        """
        # Calculate year and month after adding N months
        year = effective_date.year + (effective_date.month + months - 1) // 12
        month = (effective_date.month + months - 1) % 12 + 1

        # Calculate last day of target month
        last_day = calendar.monthrange(year, month)[1]

        # Use original day if it fits, otherwise use last day of month
        day = min(effective_date.day, last_day)

        return date(year, month, day)


class FilterChain:
    def __init__(self, filters: List[SignalFilter]):
        self.filters = filters

    def run(self, ctx: FilterContext) -> FilterOutcome:
        for filter_unit in self.filters:
            outcome = filter_unit.apply(ctx)
            if outcome.action != FilterAction.CONTINUE:
                return outcome
        return FilterOutcome(FilterAction.ACCEPT, signal=ctx.signal)
