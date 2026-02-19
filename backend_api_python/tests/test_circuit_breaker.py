"""
Tests for P1c: CircuitBreaker and portfolio_monitor_task.
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from app.services.circuit_breaker import (
    CircuitBreaker,
    get_circuit_breaker,
    reset_circuit_breaker,
)


def _cb_config(enabled=True, max_dd=15.0, recovery=10.0, cooldown_min=60):
    return {
        "multi_strategy": {
            "enabled": True,
            "circuit_breaker": {
                "enabled": enabled,
                "max_drawdown_pct": max_dd,
                "recovery_threshold_pct": recovery,
                "cooldown_minutes": cooldown_min,
            },
        },
    }


# ── CircuitBreaker core ──────────────────────────────────────────────────

class TestCircuitBreakerBasic:
    def test_no_trigger_below_threshold(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config(max_dd=15.0)
        result = cb.check(90000, config)  # 10% drawdown
        assert result is False
        assert cb.is_triggered is False

    def test_triggers_at_threshold(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config(max_dd=15.0)
        result = cb.check(84000, config)  # 16% drawdown
        assert result is True
        assert cb.is_triggered is True

    def test_exact_threshold_triggers(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config(max_dd=15.0)
        result = cb.check(85000, config)  # exactly 15%
        assert result is True

    def test_peak_tracks_up(self):
        cb = CircuitBreaker()
        config = _cb_config(max_dd=15.0)
        cb.check(100000, config)
        assert cb.peak_equity == 100000
        cb.check(110000, config)
        assert cb.peak_equity == 110000
        cb.check(105000, config)
        assert cb.peak_equity == 110000  # doesn't decrease

    def test_disabled_never_triggers(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config(enabled=False)
        result = cb.check(50000, config)  # 50% drawdown
        assert result is False
        assert cb.is_triggered is False


class TestCircuitBreakerRecovery:
    def test_stays_triggered_during_cooldown(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config(max_dd=15.0, recovery=10.0, cooldown_min=60)
        cb.check(84000, config)  # trigger
        assert cb.is_triggered is True

        # recover to 5% drawdown but cooldown not elapsed
        result = cb.check(95000, config)
        assert result is True  # still triggered

    def test_recovers_after_cooldown(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config(max_dd=15.0, recovery=10.0, cooldown_min=0)  # 0 min cooldown
        cb.check(84000, config)  # trigger
        assert cb.is_triggered is True

        # With 0 cooldown, recovery below threshold should work
        result = cb.check(95000, config)  # 5% drawdown
        assert result is False
        assert cb.is_triggered is False

    def test_no_recovery_if_drawdown_still_high(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config(max_dd=15.0, recovery=10.0, cooldown_min=0)
        cb.check(84000, config)  # trigger

        result = cb.check(89000, config)  # 11% drawdown, above recovery threshold
        assert result is True


class TestCircuitBreakerReset:
    def test_manual_reset(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config(max_dd=15.0)
        cb.check(80000, config)  # trigger
        assert cb.is_triggered is True

        cb.reset()
        assert cb.is_triggered is False

    def test_reset_peak(self):
        cb = CircuitBreaker()
        cb.reset_peak(50000)
        assert cb.peak_equity == 50000


class TestCircuitBreakerStatus:
    def test_status_structure(self):
        cb = CircuitBreaker()
        cb.reset_peak(100000)
        config = _cb_config()
        cb.check(90000, config)
        status = cb.get_status(config)
        assert "enabled" in status
        assert "triggered" in status
        assert "peak_equity" in status
        assert "current_equity" in status
        assert "current_drawdown_pct" in status
        assert "cooldown_remaining_minutes" in status


class TestCircuitBreakerSingleton:
    def test_singleton(self):
        reset_circuit_breaker()
        a = get_circuit_breaker()
        b = get_circuit_breaker()
        assert a is b
        reset_circuit_breaker()


# ── portfolio_monitor_task ────────────────────────────────────────────────

class TestPortfolioMonitorTask:
    @patch("app.tasks.portfolio_monitor_task._emergency_stop_all")
    @patch("app.services.circuit_breaker.get_circuit_breaker")
    @patch("app.services.portfolio_allocator.get_portfolio_allocator")
    @patch("app.tasks.regime_switch._load_config")
    def test_triggers_emergency_stop(self, mock_config, mock_alloc, mock_breaker, mock_stop):
        mock_config.return_value = _cb_config(max_dd=15.0)

        mock_allocator = MagicMock()
        mock_allocator.get_portfolio_summary.return_value = {
            "total_equity": 100000,
            "total_unrealized_pnl": -20000,
        }
        mock_alloc.return_value = mock_allocator

        mock_cb = MagicMock()
        mock_cb.is_triggered = False
        mock_cb.check.return_value = True  # newly triggered
        mock_cb.get_status.return_value = {
            "enabled": True, "triggered": True, "peak_equity": 100000,
            "current_equity": 80000, "current_drawdown_pct": 20.0,
            "cooldown_remaining_minutes": 60.0,
        }
        mock_breaker.return_value = mock_cb

        from app.tasks.portfolio_monitor_task import run
        run()

        mock_stop.assert_called_once()

    @patch("app.tasks.portfolio_monitor_task._emergency_stop_all")
    @patch("app.services.circuit_breaker.get_circuit_breaker")
    @patch("app.services.portfolio_allocator.get_portfolio_allocator")
    @patch("app.tasks.regime_switch._load_config")
    def test_no_stop_when_not_triggered(self, mock_config, mock_alloc, mock_breaker, mock_stop):
        mock_config.return_value = _cb_config(max_dd=15.0)

        mock_allocator = MagicMock()
        mock_allocator.get_portfolio_summary.return_value = {
            "total_equity": 100000,
            "total_unrealized_pnl": -5000,
        }
        mock_alloc.return_value = mock_allocator

        mock_cb = MagicMock()
        mock_cb.is_triggered = False
        mock_cb.check.return_value = False
        mock_cb.get_status.return_value = {
            "enabled": True, "triggered": False, "peak_equity": 100000,
            "current_equity": 95000, "current_drawdown_pct": 5.0,
            "cooldown_remaining_minutes": 0,
        }
        mock_breaker.return_value = mock_cb

        from app.tasks.portfolio_monitor_task import run
        run()

        mock_stop.assert_not_called()

    @patch("app.tasks.regime_switch._load_config")
    def test_skips_when_disabled(self, mock_config):
        mock_config.return_value = {"multi_strategy": {"enabled": False}}

        from app.tasks.portfolio_monitor_task import run
        run()  # should not raise
