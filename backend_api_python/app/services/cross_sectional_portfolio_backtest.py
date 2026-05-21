"""
BT-01：截面多标的组合回测编排（后端内核）。

- 契约：指标层 scores+weights（见 run_cross_sectional_indicator）；本服务不做 score→weight 推导。
- 执行语义：复用 CrossSectionalRunner._filter_phase21_signals 与 Phase 21 元数据口径。
- 权重归一化（Phase 22 / CONTEXT Discretion）：策略 **B** — 引擎对**严格正**权重按总和自动归一化；
  严格负权重拒绝（仅做多）；若 sum<=0 则契约失败。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
from unittest.mock import MagicMock

from app.services.backtest import BacktestService
from app.services.nq100_sources import resolve_shifted_execution_date
from app.services.universe_nq100_service import get_constituents_as_of
from app.strategies.cross_sectional_indicator import run_cross_sectional_indicator
from app.strategies.cross_sectional_weighted_signals import generate_cross_sectional_weighted_signals
from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner, ExecutionPolicy
from app.utils.logger import get_logger

logger = get_logger(__name__)

LONG_ONLY_ERR = "CROSS_SECTIONAL_LONG_ONLY:"
WEIGHT_SUM_ERR = "CROSS_SECTIONAL_WEIGHT_SUM:"


def _to_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")[:10]).date()
    raise ValueError(f"Unsupported date value: {value!r}")


def _index_dates(df: pd.DataFrame) -> List[date]:
    out: List[date] = []
    for t in df.index:
        ts = pd.Timestamp(t)
        out.append(ts.date())
    return out


def _master_calendar(panel: Mapping[str, pd.DataFrame]) -> List[date]:
    acc: set[date] = set()
    for df in panel.values():
        if df is None or getattr(df, "empty", True):
            continue
        acc.update(_index_dates(df))
    return sorted(acc)


def _slice_panel(panel: Mapping[str, pd.DataFrame], as_of: date) -> Dict[str, pd.DataFrame]:
    ts_cut = pd.Timestamp(as_of)
    out: Dict[str, pd.DataFrame] = {}
    for sym, df in panel.items():
        if df is None or df.empty:
            continue
        sub = df[df.index.normalize() <= ts_cut.normalize()]
        if not sub.empty:
            out[sym] = sub
    return out


def _row_on(df: Optional[pd.DataFrame], on: date) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    ts = pd.Timestamp(on)
    sub = df[df.index.normalize() == ts.normalize()]
    if sub.empty:
        return None
    return sub.iloc[-1]


def _resolve_pit_symbols(request: Mapping[str, Any], signal_date: date, panel_keys: set[str]) -> List[str]:
    symbol_list = request.get("symbol_list") or []
    universe = (request.get("universe") or "").strip().lower()

    if symbol_list and universe:
        raise ValueError("symbol_list and universe are mutually exclusive")

    if symbol_list:
        return sorted({str(s).strip().upper() for s in symbol_list if str(s).strip().upper() in panel_keys})

    if universe in ("nq100",):
        pit = {str(s).strip().upper() for s in get_constituents_as_of(signal_date)}
        return sorted(pit & panel_keys)

    raise ValueError("Either symbol_list or universe (nq100) is required")


def industry_neutral_residual_scores(
    scores: Mapping[str, float],
    industry_by_symbol: Mapping[str, str],
) -> Dict[str, float]:
    """
    截面行业中性：按行业分组的组内去均值（行业 FE 的 OLS 残差在仅截距模型下等价于组内去均值）。
    无行业映射的标的归入 ``_DEFAULT`` 组。
    """
    if not scores:
        return {}
    rows = []
    for sym, sc in scores.items():
        rows.append(
            {
                "symbol": sym,
                "score": float(sc),
                "ind": str(industry_by_symbol.get(sym, "_DEFAULT")),
            }
        )
    df = pd.DataFrame(rows)
    df["resid"] = df["score"] - df.groupby("ind")["score"].transform("mean")
    return {r["symbol"]: float(r["resid"]) for _, r in df.iterrows()}


def _normalize_positive_weights_b(weights: Mapping[str, float]) -> Dict[str, float]:
    """策略 B：仅允许非负权重；按正数部分之和归一化。"""
    wpos = {str(s).upper(): float(v) for s, v in weights.items() if float(v) > 0}
    if not wpos:
        raise ValueError(f"{WEIGHT_SUM_ERR} no positive weights after filtering")
    ssum = sum(wpos.values())
    if ssum <= 0:
        raise ValueError(f"{WEIGHT_SUM_ERR} weight sum must be positive")
    return {s: v / ssum for s, v in wpos.items()}


def _reject_negative_weights(weights: Mapping[str, float]) -> None:
    for s, v in weights.items():
        if float(v) < 0:
            raise ValueError(f"{LONG_ONLY_ERR} negative weight for {s!r}")


def _mask_weights_for_neutral_on(
    raw_weights: Mapping[str, float],
    neutral_scores: Mapping[str, float],
) -> Dict[str, float]:
    """用行业中性残差>0 过滤后再做策略 B 归一化。"""
    keep = {s: float(raw_weights[s]) for s in raw_weights if neutral_scores.get(s, float("-inf")) > 0.0}
    if not keep:
        best = max(raw_weights.keys(), key=lambda k: neutral_scores.get(k, float("-inf")))
        keep = {best: float(raw_weights[best])}
    return _normalize_positive_weights_b(keep)


def _next_calendar_date(cal: Sequence[date], current: date) -> Optional[date]:
    for d in cal:
        if d > current:
            return d
    return None


def _build_execution_metadata(
    panel: Mapping[str, pd.DataFrame],
    execution_trade_date: date,
    symbols: Sequence[str],
    ic_effective_dates: Sequence[Any],
) -> Dict[str, Any]:
    market_rows: Dict[str, Any] = {}
    for sym in symbols:
        row = _row_on(panel.get(sym), execution_trade_date)
        if row is None:
            continue
        o = float(row.get("open", row.get("close", 0.0)) or 0.0)
        c = float(row.get("close", o) or 0.0)
        vol = float(row.get("volume", 0.0) or 0.0)
        adv = abs(o * vol) if vol else 5_000_000.0
        market_rows[sym] = {
            "next_open": o if o > 0 else c,
            "open": o,
            "close": c,
            "adv20_usd": max(adv, 5_000_000.0),
        }
    eff = [_to_date(x) for x in ic_effective_dates]
    return {
        "market_rows": market_rows,
        "tradability": {s: "TRADABLE" for s in symbols},
        "cash_mna": {},
        "ic_effective_dates": eff,
    }


def _simulate_equity_path(
    panel: Mapping[str, pd.DataFrame],
    calendar: List[date],
    weight_schedule: List[Tuple[date, date, Dict[str, float]]],
    initial_capital: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    weight_schedule: (signal_date, execution_trade_date, target_weights)
    在 execution 日开盘按目标权重全仓再平衡；日末用 close 做市值。
    """
    holdings: Dict[str, float] = {}
    cash = float(initial_capital)
    trades: List[Dict[str, Any]] = []

    exec_map: Dict[date, Dict[str, float]] = {}
    for _sig, exe, tw in weight_schedule:
        exec_map[exe] = tw

    equity_curve: List[Dict[str, Any]] = []

    for d in calendar:
        if d in exec_map:
            tw = exec_map[d]
            open_px: Dict[str, float] = {}
            for sym in tw:
                row = _row_on(panel.get(sym), d)
                if row is None:
                    continue
                px = float(row.get("open", row.get("close", 0.0)) or 0.0)
                if px > 0:
                    open_px[sym] = px
            twf = {s: tw[s] for s in tw if s in open_px and tw[s] > 0}
            if twf and open_px:
                pre_v = cash + sum(holdings.get(s, 0.0) * open_px.get(s, 0.0) for s in holdings)
                pre_v = max(pre_v, 1e-9)
                tw_norm = _normalize_positive_weights_b(twf)
                new_h: Dict[str, float] = {}
                for sym, w in tw_norm.items():
                    if sym not in open_px:
                        continue
                    new_h[sym] = w * pre_v / open_px[sym]
                holdings = new_h
                cash = 0.0
                trades.append({"day": d.isoformat(), "type": "rebalance"})

        close_px: Dict[str, float] = {}
        for sym in holdings:
            rowc = _row_on(panel.get(sym), d)
            if rowc is None:
                continue
            c = float(rowc.get("close", 0.0) or 0.0)
            if c > 0:
                close_px[sym] = c
        mtm = cash + sum(holdings[s] * close_px.get(s, 0.0) for s in holdings)
        equity_curve.append({"time": d.isoformat(), "value": float(mtm)})

    return equity_curve, trades


def _simulate_with_runner(
    panel: Mapping[str, pd.DataFrame],
    calendar: List[date],
    rebalance_dates: List[date],
    indicator_code: str,
    trading_config: Mapping[str, Any],
    initial_capital: float,
    timeframe: str,
    industry_by_symbol: Mapping[str, str],
    neutral_mode: str,
    request: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """neutral_mode: 'off' | 'on'"""
    runner = CrossSectionalRunner(MagicMock(), MagicMock())
    policy = ExecutionPolicy.from_config(dict(trading_config))
    schedule: List[Tuple[date, date, Dict[str, float]]] = []

    panel_keys = {str(k).upper() for k in panel.keys()}
    ic_raw = request.get("ic_effective_dates") or []

    for sig_d in rebalance_dates:
        if sig_d >= calendar[-1]:
            break
        pit = _resolve_pit_symbols(request, sig_d, panel_keys)
        slice_panel = _slice_panel(panel, sig_d)
        slice_panel = {k: v for k, v in slice_panel.items() if k in pit}
        if len(slice_panel) < 1:
            continue

        raw = run_cross_sectional_indicator(indicator_code, slice_panel, dict(trading_config))
        if not raw:
            continue
        scores = {str(k).upper(): float(v) for k, v in raw["scores"].items()}
        w_raw = {str(k).upper(): float(v) for k, v in raw["weights"].items() if k in slice_panel}

        _reject_negative_weights(w_raw)
        base_w = _normalize_positive_weights_b({k: w_raw[k] for k in w_raw if k in pit})

        if neutral_mode == "off":
            final_w = _normalize_positive_weights_b(base_w)
        else:
            resid = industry_neutral_residual_scores(scores, industry_by_symbol)
            final_w = _mask_weights_for_neutral_on(base_w, resid)

        raw_next = _next_calendar_date(calendar, sig_d)
        if raw_next is None:
            continue
        eff_dates = [_to_date(x) for x in ic_raw]
        exec_trade_date = resolve_shifted_execution_date(sig_d, raw_next, eff_dates)

        positions: List[Dict[str, Any]] = []
        sigs = generate_cross_sectional_weighted_signals(
            final_w,
            {s: 1 for s in final_w},
            positions,
        )
        dated: List[Dict[str, Any]] = []
        for s in sigs:
            dated.append(
                {
                    **s,
                    "signal_date": sig_d.isoformat(),
                    "execution_date": raw_next.isoformat(),
                }
            )

        meta = _build_execution_metadata(panel, exec_trade_date, list(final_w.keys()), ic_raw)
        accepted, _m = runner._filter_phase21_signals(dated, policy, meta)  # pylint: disable=protected-access

        exec_weights: Dict[str, float] = {}
        for sig in accepted:
            if sig.get("type") == "open_long" and sig.get("symbol"):
                tw = float(sig.get("target_weight", sig.get("position_size", 0.0)) or 0.0)
                if tw > 0:
                    exec_weights[str(sig["symbol"]).upper()] = tw
        if not exec_weights:
            exec_weights = dict(final_w)

        exec_weights = _normalize_positive_weights_b(exec_weights)
        schedule.append((sig_d, exec_trade_date, exec_weights))

    equity_curve, trades = _simulate_equity_path(panel, calendar, schedule, initial_capital)

    start_dt = datetime.combine(calendar[0], datetime.min.time())
    end_dt = datetime.combine(calendar[-1], datetime.min.time())
    bt = BacktestService()
    metrics = bt._calculate_metrics(  # pylint: disable=protected-access
        equity_curve,
        trades,
        initial_capital,
        timeframe,
        start_dt,
        end_dt,
        0.0,
    )
    formatted = bt._format_result(metrics, equity_curve, trades)  # pylint: disable=protected-access
    summary = {k: v for k, v in formatted.items() if k not in ("equityCurve", "trades")}
    repro = {
        "neutral_mode": neutral_mode,
        "timeframe": timeframe,
        "rebalance_dates": [d.isoformat() for d in rebalance_dates],
        "weight_schedule_len": len(schedule),
    }
    return formatted.get("equityCurve", equity_curve), summary, repro


class CrossSectionalPortfolioBacktestService:
    """截面组合回测：单组合、neutral_off / neutral_on 双套完整输出。"""

    def run(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raw_panel = request.get("panel") or {}
        if not isinstance(raw_panel, dict) or not raw_panel:
            raise ValueError("request.panel (symbol->DataFrame) is required")

        panel = {str(k).strip().upper(): v for k, v in raw_panel.items()}

        trading_config = dict(request.get("trading_config") or {})
        initial_capital = float(trading_config.get("initial_capital", 100_000.0))
        timeframe = str(trading_config.get("timeframe", "1D"))
        start = _to_date(request["start_date"])
        end = _to_date(request["end_date"])
        indicator_code = str(request.get("indicator_code") or "")
        if not indicator_code.strip():
            raise ValueError("indicator_code is required")

        industry_by_symbol = {str(k).upper(): str(v) for k, v in (request.get("industry_by_symbol") or {}).items()}

        calendar = [d for d in _master_calendar(panel) if start <= d <= end]
        if len(calendar) < 2:
            raise ValueError("insufficient calendar overlap in panel for [start_date,end_date]")

        freq = str(trading_config.get("rebalance_frequency", "daily")).lower()
        if freq == "daily":
            rebalance_dates = calendar[:-1]
        elif freq == "weekly":
            rebalance_dates = [calendar[0]] + calendar[5::5]
            rebalance_dates = [d for d in rebalance_dates if d < calendar[-1]]
        else:
            rebalance_dates = calendar[:-1]

        off_curve, off_sum, off_repro = _simulate_with_runner(
            panel,
            calendar,
            rebalance_dates,
            indicator_code,
            trading_config,
            initial_capital,
            timeframe,
            industry_by_symbol,
            "off",
            request,
        )
        on_curve, on_sum, on_repro = _simulate_with_runner(
            panel,
            calendar,
            rebalance_dates,
            indicator_code,
            trading_config,
            initial_capital,
            timeframe,
            industry_by_symbol,
            "on",
            request,
        )

        digest = self._repro_digest(request, off_curve, on_curve)
        return {
            "repro_digest": digest,
            "neutral_off": {
                "equity_curve": off_curve,
                "summary": off_sum,
                "repro": {**off_repro, "neutral_branch": "off"},
            },
            "neutral_on": {
                "equity_curve": on_curve,
                "summary": on_sum,
                "repro": {**on_repro, "neutral_branch": "on"},
            },
        }

    @staticmethod
    def _repro_digest(request: Mapping[str, Any], off_curve: Any, on_curve: Any) -> str:
        payload = {
            "start_date": str(request.get("start_date")),
            "end_date": str(request.get("end_date")),
            "universe": request.get("universe"),
            "symbol_list": request.get("symbol_list"),
            "indicator_code": request.get("indicator_code"),
            "trading_config": request.get("trading_config"),
            "off_tail": (off_curve or [])[-3:],
            "on_tail": (on_curve or [])[-3:],
        }
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
