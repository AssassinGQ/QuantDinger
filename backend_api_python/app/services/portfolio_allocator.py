"""
PortfolioAllocator — 多策略资金池管理器（单例）。

核心职责：
  1. 按品种维护总资金池
  2. 根据 regime 计算每策略的权重与分配资金
  3. 供 TradingExecutor 查询 allocated capital
  4. 按品种聚合 qd_strategy_positions 计算组合持仓
"""

import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)

_allocator_instance: Optional["PortfolioAllocator"] = None
_allocator_lock = threading.Lock()


def get_portfolio_allocator() -> "PortfolioAllocator":
    """获取 PortfolioAllocator 单例。"""
    global _allocator_instance
    if _allocator_instance is None:
        with _allocator_lock:
            if _allocator_instance is None:
                _allocator_instance = PortfolioAllocator()
    return _allocator_instance


def reset_portfolio_allocator() -> None:
    """重置单例（仅测试用）。"""
    global _allocator_instance
    _allocator_instance = None


class PortfolioAllocator:
    """多策略资金池管理器。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        self._current_regime: str = "normal"
        # style → effective weight (currently applied)
        self._effective_weights: Dict[str, float] = {}
        # strategy_id → allocated capital
        self._strategy_allocation: Dict[int, float] = {}
        # strategy_id → style
        self._strategy_style: Dict[int, str] = {}
        # strategy_id → initial_capital (cached from config/DB)
        self._strategy_initial_capital: Dict[int, float] = {}
        # symbol → {style: [strategy_id, ...]}
        self._symbol_strategies: Dict[str, Dict[str, List[int]]] = {}
        # symbol → total capital pool
        self._symbol_capital_pool: Dict[str, float] = {}

    # ── 对外查询接口 ─────────────────────────────────────────────────

    def get_allocated_capital(self, strategy_id: int) -> Optional[float]:
        """TradingExecutor 调用：获取某策略当前分配到的可用资金。
        返回 None 表示该策略不由本模块管理。
        线程安全：只读 dict 查找，O(1)。
        """
        return self._strategy_allocation.get(strategy_id)

    @property
    def current_regime(self) -> str:
        return self._current_regime

    @property
    def effective_weights(self) -> Dict[str, float]:
        return dict(self._effective_weights)

    @property
    def strategy_allocation(self) -> Dict[int, float]:
        return dict(self._strategy_allocation)

    # ── 核心：regime 更新 → 重算权重与分配 ──────────────────────────

    def update_regime(
        self,
        regime: str,
        config: Dict[str, Any],
        symbol_strategies: Dict[str, Dict[str, List[int]]],
        strategy_initial_capitals: Optional[Dict[int, float]] = None,
    ) -> Dict[str, Any]:
        """regime_switch 调用：更新 regime 并重新计算所有分配。

        Args:
            regime: 当前 regime（panic/high_vol/normal/low_vol）
            config: 完整配置 dict
            symbol_strategies: {symbol: {style: [sid, ...]}}
            strategy_initial_capitals: {sid: initial_capital} 可选，不传则使用缓存

        Returns:
            {"started": [...], "stopped": [...], "weight_changed": [...]}
        """
        with self._lock:
            ms_cfg = config.get("multi_strategy", {})

            self._current_regime = regime
            self._symbol_strategies = symbol_strategies

            if strategy_initial_capitals:
                self._strategy_initial_capital.update(strategy_initial_capitals)

            self._rebuild_strategy_style_map()

            target_weights = self._get_target_weights(regime, ms_cfg)
            min_threshold = ms_cfg.get("min_weight_threshold", 0.05)
            effective = _apply_threshold(target_weights, min_threshold)
            effective = _normalize_weights(effective)

            old_weights = dict(self._effective_weights)
            self._effective_weights = effective

            self._compute_allocations(ms_cfg)

            ids_to_stop, ids_to_start = self._compute_start_stop_diff(config)

            result: Dict[str, Any] = {
                "started": ids_to_start,
                "stopped": ids_to_stop,
                "weight_changed": self._find_weight_changed(old_weights, effective),
            }

            return result

    # ── 组合持仓查询 ─────────────────────────────────────────────────

    def get_combined_positions(self) -> Dict[str, Dict[str, Any]]:
        """按品种聚合所有策略的持仓。返回 {symbol: {total_long, total_short, net_exposure, ...}}"""
        try:
            from app.utils.db import get_db_connection
            managed_ids = self._get_all_managed_ids()
            if not managed_ids:
                return {}
            placeholders = ",".join(["%s"] * len(managed_ids))
            query = f"""
                SELECT strategy_id, symbol, side,
                       COALESCE(size, 0) AS size,
                       COALESCE(entry_price, 0) AS entry_price,
                       COALESCE(current_price, 0) AS current_price,
                       COALESCE(unrealized_pnl, 0) AS unrealized_pnl
                FROM qd_strategy_positions
                WHERE strategy_id IN ({placeholders}) AND COALESCE(size, 0) > 0
            """
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(query, tuple(managed_ids))
                rows = cur.fetchall()
                cur.close()

            result: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                sym = row["symbol"]
                if sym not in result:
                    result[sym] = {
                        "symbol": sym,
                        "total_long_value": 0.0,
                        "total_short_value": 0.0,
                        "net_exposure": 0.0,
                        "unrealized_pnl": 0.0,
                        "strategies": [],
                    }
                value = float(row["size"]) * float(row["current_price"])
                pnl = float(row["unrealized_pnl"])
                side = (row["side"] or "").strip().lower()
                if side == "long":
                    result[sym]["total_long_value"] += value
                else:
                    result[sym]["total_short_value"] += value
                result[sym]["unrealized_pnl"] += pnl
                result[sym]["strategies"].append({
                    "strategy_id": row["strategy_id"],
                    "side": side,
                    "size": float(row["size"]),
                    "entry_price": float(row["entry_price"]),
                    "current_price": float(row["current_price"]),
                    "unrealized_pnl": pnl,
                })

            for sym_data in result.values():
                sym_data["net_exposure"] = sym_data["total_long_value"] - sym_data["total_short_value"]

            return result
        except Exception as e:
            logger.error("[portfolio_allocator] get_combined_positions failed: %s", e)
            return {}

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """全局组合摘要。"""
        positions = self.get_combined_positions()
        total_equity = sum(self._symbol_capital_pool.values()) if self._symbol_capital_pool else 0.0
        total_pnl = sum(p["unrealized_pnl"] for p in positions.values())
        return {
            "regime": self._current_regime,
            "weights": dict(self._effective_weights),
            "allocation": dict(self._strategy_allocation),
            "positions": positions,
            "total_equity": total_equity,
            "total_unrealized_pnl": total_pnl,
        }

    # ── 内部方法 ─────────────────────────────────────────────────────

    def _rebuild_strategy_style_map(self) -> None:
        """从 symbol_strategies 构建 strategy_id → style 映射。"""
        self._strategy_style.clear()
        for _sym, style_map in self._symbol_strategies.items():
            if not isinstance(style_map, dict):
                continue
            for style, ids in style_map.items():
                for sid in (ids or []):
                    self._strategy_style[int(sid)] = style

    def _get_target_weights(self, regime: str, ms_cfg: Dict) -> Dict[str, float]:
        """从配置中读取 regime → weights 映射。"""
        regime_to_weights = ms_cfg.get("regime_to_weights", {})
        weights = regime_to_weights.get(regime, {})
        if not weights:
            weights = {"conservative": 0.2, "balanced": 0.6, "aggressive": 0.2}
        return {k: float(v) for k, v in weights.items()}

    def _compute_allocations(self, ms_cfg: Dict) -> None:
        """根据 effective_weights 计算每策略的 allocated capital。"""
        max_alloc_ratio = ms_cfg.get("max_allocation_ratio", 2.0)
        new_alloc: Dict[int, float] = {}
        new_pools: Dict[str, float] = {}

        configured_pools = ms_cfg.get("symbol_capital_pool", {}) or {}

        for symbol, style_map in self._symbol_strategies.items():
            if not isinstance(style_map, dict):
                continue

            if symbol in configured_pools:
                pool = float(configured_pools[symbol])
            else:
                pool = self._calculate_symbol_pool(style_map)

            new_pools[symbol] = pool

            for style, ids in style_map.items():
                if not ids:
                    continue
                weight = self._effective_weights.get(style, 0.0)
                if weight <= 0:
                    for sid in ids:
                        new_alloc[int(sid)] = 0.0
                    continue
                per_strategy = pool * weight / len(ids)
                for sid in ids:
                    sid = int(sid)
                    cap = per_strategy
                    orig = self._strategy_initial_capital.get(sid, 0.0)
                    if orig > 0:
                        cap = min(cap, orig * max_alloc_ratio)
                    new_alloc[sid] = cap

        self._strategy_allocation = new_alloc
        self._symbol_capital_pool = new_pools

    def _calculate_symbol_pool(self, style_map: Dict[str, List[int]]) -> float:
        """未配置 symbol_capital_pool 时，取该品种所有策略 initial_capital 的最大值 × style 数。
        若无 initial_capital 信息则返回 0。"""
        max_ic = 0.0
        style_count = 0
        for style, ids in style_map.items():
            if not ids:
                continue
            style_count += 1
            for sid in ids:
                ic = self._strategy_initial_capital.get(int(sid), 0.0)
                max_ic = max(max_ic, ic)
        return max_ic * style_count if max_ic > 0 else 0.0

    def _compute_start_stop_diff(self, config: Dict) -> Tuple[List[int], List[int]]:
        """计算需要停止和启动的策略 ID。weight=0 → 停止，weight>0 且未运行 → 启动。"""
        ids_to_stop: List[int] = []
        ids_to_start: List[int] = []

        try:
            running_ids = self._get_running_ids()
        except Exception:
            running_ids = set()

        all_managed = self._get_all_managed_ids()

        for sid in all_managed:
            alloc = self._strategy_allocation.get(sid, 0.0)
            is_running = sid in running_ids
            if alloc <= 0 and is_running:
                ids_to_stop.append(sid)
            elif alloc > 0 and not is_running:
                ids_to_start.append(sid)

        return sorted(ids_to_stop), sorted(ids_to_start)

    def _get_running_ids(self) -> Set[int]:
        from app import get_trading_executor
        executor = get_trading_executor()
        with executor.lock:
            return set(executor.running_strategies.keys())

    def _get_all_managed_ids(self) -> Set[int]:
        ids: Set[int] = set()
        for _sym, style_map in self._symbol_strategies.items():
            if not isinstance(style_map, dict):
                continue
            for id_list in style_map.values():
                if isinstance(id_list, list):
                    ids.update(int(i) for i in id_list)
        return ids

    def _find_weight_changed(
        self, old_weights: Dict[str, float], new_weights: Dict[str, float]
    ) -> List[int]:
        """找出权重发生变化的策略 ID。"""
        changed_styles: Set[str] = set()
        all_styles = set(old_weights) | set(new_weights)
        for s in all_styles:
            if abs(old_weights.get(s, 0.0) - new_weights.get(s, 0.0)) > 1e-6:
                changed_styles.add(s)

        changed_ids: List[int] = []
        for sid, style in self._strategy_style.items():
            if style in changed_styles:
                changed_ids.append(sid)
        return sorted(changed_ids)


# ── 工具函数 ──────────────────────────────────────────────────────────

def _apply_threshold(weights: Dict[str, float], threshold: float) -> Dict[str, float]:
    """权重低于 threshold 的置为 0。"""
    return {k: (v if v >= threshold else 0.0) for k, v in weights.items()}


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """归一化：确保正权重之和为 1.0。若全部为 0 则不变。"""
    total = sum(v for v in weights.values() if v > 0)
    if total <= 0:
        return dict(weights)
    return {k: (v / total if v > 0 else 0.0) for k, v in weights.items()}
