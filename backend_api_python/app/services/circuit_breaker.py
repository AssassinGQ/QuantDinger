"""
CircuitBreaker — 组合回撤熔断器。

当组合 equity 从峰值回撤超过阈值时触发熔断，暂停所有被管理策略。
回撤恢复到 recovery_threshold 以下且冷却期结束后自动解除。
"""

import threading
import time
from typing import Any, Dict, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

_breaker_instance: Optional["CircuitBreaker"] = None
_breaker_lock = threading.Lock()


def get_circuit_breaker() -> "CircuitBreaker":
    global _breaker_instance
    if _breaker_instance is None:
        with _breaker_lock:
            if _breaker_instance is None:
                _breaker_instance = CircuitBreaker()
    return _breaker_instance


def reset_circuit_breaker() -> None:
    global _breaker_instance
    _breaker_instance = None


class CircuitBreaker:
    """组合回撤熔断器。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._peak_equity: float = 0.0
        self._is_triggered: bool = False
        self._trigger_time: Optional[float] = None
        self._last_equity: float = 0.0

    @property
    def is_triggered(self) -> bool:
        return self._is_triggered

    @property
    def peak_equity(self) -> float:
        return self._peak_equity

    def get_status(self, config: Optional[Dict] = None) -> Dict[str, Any]:
        """返回熔断器状态。"""
        cb_cfg = (config or {}).get("multi_strategy", {}).get("circuit_breaker", {})
        enabled = cb_cfg.get("enabled", False)
        dd_pct = self._compute_drawdown_pct()
        cooldown_remaining = 0.0
        if self._is_triggered and self._trigger_time:
            cooldown_min = cb_cfg.get("cooldown_minutes", 60)
            elapsed = (time.time() - self._trigger_time) / 60.0
            cooldown_remaining = max(0.0, cooldown_min - elapsed)

        return {
            "enabled": enabled,
            "triggered": self._is_triggered,
            "peak_equity": self._peak_equity,
            "current_equity": self._last_equity,
            "current_drawdown_pct": dd_pct,
            "cooldown_remaining_minutes": round(cooldown_remaining, 1),
        }

    def check(self, current_equity: float, config: Dict) -> bool:
        """检查是否触发/解除熔断。返回 True 表示当前处于熔断状态。

        调用方（portfolio_monitor_task）需传入实时组合 equity。
        """
        cb_cfg = config.get("multi_strategy", {}).get("circuit_breaker", {})
        if not cb_cfg.get("enabled", False):
            return False

        max_dd = float(cb_cfg.get("max_drawdown_pct", 15.0))
        recovery = float(cb_cfg.get("recovery_threshold_pct", 10.0))
        cooldown_min = float(cb_cfg.get("cooldown_minutes", 60))

        with self._lock:
            self._last_equity = current_equity

            if current_equity > self._peak_equity:
                self._peak_equity = current_equity

            dd_pct = self._compute_drawdown_pct()

            if not self._is_triggered:
                if dd_pct >= max_dd:
                    self._is_triggered = True
                    self._trigger_time = time.time()
                    logger.warning(
                        "[circuit_breaker] TRIGGERED: drawdown=%.1f%% >= %.1f%%, peak=%.0f current=%.0f",
                        dd_pct, max_dd, self._peak_equity, current_equity,
                    )
                    return True
            else:
                elapsed_min = (time.time() - (self._trigger_time or 0)) / 60.0
                if dd_pct < recovery and elapsed_min >= cooldown_min:
                    self._is_triggered = False
                    self._trigger_time = None
                    logger.info(
                        "[circuit_breaker] RECOVERED: drawdown=%.1f%% < %.1f%%, cooldown elapsed",
                        dd_pct, recovery,
                    )
                    return False

            return self._is_triggered

    def reset(self) -> None:
        """手动解除熔断。"""
        with self._lock:
            was_triggered = self._is_triggered
            self._is_triggered = False
            self._trigger_time = None
            if was_triggered:
                logger.info("[circuit_breaker] manually reset")

    def reset_peak(self, equity: float = 0.0) -> None:
        """重置峰值（测试或初始化用）。"""
        with self._lock:
            self._peak_equity = equity
            self._last_equity = equity

    def _compute_drawdown_pct(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        return (self._peak_equity - self._last_equity) / self._peak_equity * 100.0
