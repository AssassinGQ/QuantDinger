"""BT-01：截面组合回测契约、引擎、PIT、行业中性、仅做多与权重归一化。"""

from __future__ import annotations

from datetime import date, timedelta
import json
from unittest.mock import patch

import pandas as pd
import pytest
from flask import Flask

from app.services.cross_sectional_portfolio_backtest import (
    CrossSectionalPortfolioBacktestService,
    industry_neutral_residual_scores,
)
from app.strategies.cross_sectional_indicator import run_cross_sectional_indicator


def _daily_panel(symbols, start: date, n_days: int, base_price: float = 100.0) -> dict:
    out = {}
    for j, sym in enumerate(symbols):
        idx = [pd.Timestamp(start + timedelta(days=i)) for i in range(n_days)]
        p0 = base_price * (1 + 0.01 * j)
        rows = []
        for i in range(n_days):
            c = p0 * (1 + 0.001 * i)
            o = c * 0.999
            rows.append({"open": o, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6})
        out[sym] = pd.DataFrame(rows, index=idx)
    return out


class TestIndicatorContract:
    """22-01 Task 1"""

    def test_indicator_contract_ok(self):
        idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.0],
                "volume": [1e6, 1e6],
            },
            index=idx,
        )
        data = {"AAA": df.copy(), "BBB": df.copy()}
        code = (
            "for s in symbols:\n"
            "    scores[s] = 1.0\n"
            "    weights[s] = 0.5\n"
            "rankings = list(symbols)"
        )
        raw = run_cross_sectional_indicator(code, data, {})
        assert raw is not None
        assert set(raw.keys()) >= {"scores", "weights", "rankings"}
        assert len(raw["weights"]) == 2

    def test_indicator_contract_missing_weights_raises(self):
        idx = pd.to_datetime(["2024-01-02"])
        df = pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1e6]},
            index=idx,
        )
        data = {"AAA": df, "BBB": df}
        code = "scores = {s: 1.0 for s in symbols}; rankings = list(symbols)"
        with pytest.raises(ValueError, match="CROSS_SECTIONAL_CONTRACT"):
            run_cross_sectional_indicator(code, data, {})

    def test_indicator_contract_missing_scores_raises(self):
        idx = pd.to_datetime(["2024-01-02"])
        df = pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1e6]},
            index=idx,
        )
        data = {"AAA": df, "BBB": df}
        code = "weights = {s: 0.5 for s in symbols}; rankings = list(symbols)"
        with pytest.raises(ValueError, match="CROSS_SECTIONAL_CONTRACT"):
            run_cross_sectional_indicator(code, data, {})


class TestEngineCore:
    """22-01 Task 2"""

    def test_engine_core_equity_and_repro(self):
        start = date(2024, 1, 2)
        panel = _daily_panel(["AAA", "BBB"], start, 8)
        code = (
            "for s in symbols:\n"
            "    scores[s] = 1.0\n"
            "    weights[s] = 1.0 / len(symbols)\n"
            "rankings = list(symbols)"
        )
        req = {
            "panel": panel,
            "symbol_list": ["AAA", "BBB"],
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=7)).isoformat(),
            "indicator_code": code,
            "trading_config": {"initial_capital": 100_000.0, "timeframe": "1D", "rebalance_frequency": "daily"},
        }
        svc = CrossSectionalPortfolioBacktestService()
        a = svc.run(req)
        b = svc.run(req)
        assert a["repro_digest"] == b["repro_digest"]
        off = a["neutral_off"]["equity_curve"]
        assert len(off) >= 5
        assert all(isinstance(x.get("value"), (int, float)) for x in off)
        assert all(pd.notna(x.get("value")) for x in off)


class TestPitUniverse:
    """22-01-02b PIT：T 日无 SYM，T+k 才进入池"""

    def test_pit_excludes_future_effective_symbol(self):
        start = date(2024, 1, 2)
        panel = _daily_panel(["AAA", "SYM"], start, 10)

        def constituents_as_of(d: date):
            if d <= date(2024, 1, 5):
                return ["AAA"]
            return ["AAA", "SYM"]

        from app.services import cross_sectional_portfolio_backtest as mod

        req = {
            "panel": panel,
            "universe": "nq100",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=9)).isoformat(),
            "indicator_code": (
                "for s in symbols:\n"
                "    scores[s] = float(len(symbols))\n"
                "    weights[s] = 1.0 / len(symbols)\n"
                "rankings = sorted(symbols, key=lambda x: scores[x], reverse=True)"
            ),
            "trading_config": {"initial_capital": 100_000.0, "timeframe": "1D", "rebalance_frequency": "daily"},
        }
        with patch.object(mod, "get_constituents_as_of", side_effect=constituents_as_of):
            pit_early = mod._resolve_pit_symbols(req, date(2024, 1, 3), {"AAA", "SYM"})
            pit_late = mod._resolve_pit_symbols(req, date(2024, 1, 8), {"AAA", "SYM"})
        assert pit_early == ["AAA"]
        assert set(pit_late) == {"AAA", "SYM"}

        with patch(
            "app.services.cross_sectional_portfolio_backtest.get_constituents_as_of",
            side_effect=constituents_as_of,
        ):
            out = CrossSectionalPortfolioBacktestService().run(req)
        assert out["neutral_off"]["summary"]["totalReturn"] is not None


class TestNeutralDual:
    """22-01 Task 3"""

    def test_neutral_off_on_both_summaries(self):
        start = date(2024, 1, 2)
        panel = _daily_panel(["AAA", "BBB"], start, 10)
        code = (
            "for s in symbols:\n"
            "    scores[s] = 1.0 if s == 'AAA' else 2.0\n"
            "    weights[s] = 0.5\n"
            "rankings = sorted(symbols, key=lambda x: scores[x], reverse=True)"
        )
        req = {
            "panel": panel,
            "symbol_list": ["AAA", "BBB"],
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=9)).isoformat(),
            "indicator_code": code,
            "industry_by_symbol": {"AAA": "X", "BBB": "Y"},
            "trading_config": {"initial_capital": 100_000.0, "timeframe": "1D", "rebalance_frequency": "daily"},
        }
        out = CrossSectionalPortfolioBacktestService().run(req)
        assert "neutral_off" in out and "neutral_on" in out
        assert isinstance(out["neutral_off"]["summary"], dict)
        assert isinstance(out["neutral_on"]["summary"], dict)
        assert set(out["neutral_off"]["summary"].keys()) == set(out["neutral_on"]["summary"].keys())

    def test_neutral_residual_changes_ranking_toy(self):
        scores = {"AAA": 0.1, "BBB": 0.9}
        ind = {"AAA": "G1", "BBB": "G1"}
        resid = industry_neutral_residual_scores(scores, ind)
        assert abs(resid["AAA"] + resid["BBB"]) < 1e-9


class TestLongOnlyWeightNorm:
    """22-01 Task 4"""

    def test_negative_weight_rejected_in_service(self):
        start = date(2024, 1, 2)
        panel = _daily_panel(["AAA", "BBB"], start, 6)
        code = (
            "scores = {s: 1.0 for s in symbols}\n"
            "weights = {symbols[0]: 0.6, symbols[1]: -0.1}\n"
            "rankings = list(symbols)"
        )
        req = {
            "panel": panel,
            "symbol_list": ["AAA", "BBB"],
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=5)).isoformat(),
            "indicator_code": code,
            "trading_config": {"initial_capital": 100_000.0, "timeframe": "1D"},
        }
        with pytest.raises(ValueError, match="CROSS_SECTIONAL_LONG_ONLY"):
            CrossSectionalPortfolioBacktestService().run(req)

    def test_strategy_b_normalizes_unequal_sum(self):
        start = date(2024, 1, 2)
        panel = _daily_panel(["AAA", "BBB"], start, 6)
        code = (
            "scores = {s: 1.0 for s in symbols}\n"
            "weights = {s: 0.4 for s in symbols}\n"
            "rankings = list(symbols)"
        )
        req = {
            "panel": panel,
            "symbol_list": ["AAA", "BBB"],
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=5)).isoformat(),
            "indicator_code": code,
            "trading_config": {"initial_capital": 100_000.0, "timeframe": "1D"},
        }
        out = CrossSectionalPortfolioBacktestService().run(req)
        assert out["neutral_off"]["equity_curve"][-1]["value"] > 0


@pytest.fixture
def cs_bt_http_client():
    from app.routes.cross_sectional_portfolio_backtest import cross_sectional_portfolio_bt_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(cross_sectional_portfolio_bt_bp, url_prefix="/api/indicator")

    with app.test_client() as c:
        yield c


AUTH = {"Authorization": "Bearer testtoken"}


@patch("app.utils.auth.verify_token", return_value={"sub": "u1", "user_id": 1, "role": "user"})
class TestCrossSectionalPortfolioHttp:
    def test_pool_validation_mutual_exclusive(self, _tok, cs_bt_http_client):
        resp = cs_bt_http_client.post(
            "/api/indicator/cross-sectional-portfolio-backtest",
            data=json.dumps(
                {
                    "symbolList": ["AAPL"],
                    "universe": "NQ100",
                    "indicatorCode": "x=1",
                    "startDate": "2024-01-02",
                    "endDate": "2024-01-10",
                }
            ),
            content_type="application/json",
            headers=AUTH,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == 0
        assert body["data"] is None
        assert "Traceback" not in (body.get("msg") or "")
        assert "symbolList" in body["msg"] or "universe" in body["msg"]

    def test_pool_validation_both_empty(self, _tok, cs_bt_http_client):
        resp = cs_bt_http_client.post(
            "/api/indicator/cross-sectional-portfolio-backtest",
            json={
                "symbolList": [],
                "universe": "",
                "indicatorCode": "x=1",
                "startDate": "2024-01-02",
                "endDate": "2024-01-10",
            },
            headers=AUTH,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == 0

    def test_route_register_not_404(self, _tok, cs_bt_http_client):
        resp = cs_bt_http_client.post(
            "/api/indicator/cross-sectional-portfolio-backtest",
            json={
                "symbolList": ["AAPL"],
                "universe": "",
                "indicatorCode": "x=1",
                "startDate": "2024-01-02",
                "endDate": "2024-01-10",
            },
            headers=AUTH,
        )
        assert resp.status_code != 404

    def test_bogus_path_404(self, _tok, cs_bt_http_client):
        resp = cs_bt_http_client.post(
            "/api/indicator/nonexistent_bt_phase22_xyz",
            json={},
            headers=AUTH,
        )
        assert resp.status_code == 404


@patch("app.utils.auth.verify_token", return_value={"sub": "u1", "user_id": 1, "role": "user"})
def test_api_success_structure(_tok, cs_bt_http_client):
    start = date(2024, 1, 2)
    panel = _daily_panel(["AAA", "BBB"], start, 8)
    fake_inner = {
        "repro_digest": "abc",
        "neutral_off": {
            "equity_curve": [{"time": "2024-01-02", "value": 1.0}],
            "summary": {"totalReturn": 0.0},
            "repro": {},
        },
        "neutral_on": {
            "equity_curve": [{"time": "2024-01-02", "value": 1.0}],
            "summary": {"totalReturn": 0.0},
            "repro": {},
        },
    }

    def _fake_fetch(*_a, **_k):
        return panel

    with patch(
        "app.routes.cross_sectional_portfolio_backtest._fetch_panel_for_symbols",
        side_effect=_fake_fetch,
    ), patch.object(CrossSectionalPortfolioBacktestService, "run", return_value=fake_inner):
        resp = cs_bt_http_client.post(
            "/api/indicator/cross-sectional-portfolio-backtest",
            json={
                "symbolList": ["AAA", "BBB"],
                "indicatorCode": (
                    "for s in symbols:\n"
                    "    scores[s] = 1.0\n"
                    "    weights[s] = 0.5\n"
                    "rankings = list(symbols)"
                ),
                "startDate": start.isoformat(),
                "endDate": (start + timedelta(days=7)).isoformat(),
                "timeframe": "1D",
                "market": "USStock",
            },
            headers=AUTH,
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 1
    assert body["msg"] == "OK"
    assert "neutral_off" in body["data"] and "neutral_on" in body["data"]
    assert "repro" in body["data"]
    assert "universe_digest" in body["data"]["repro"]


@patch("app.utils.auth.verify_token", return_value={"sub": "u1", "user_id": 1, "role": "user"})
def test_api_contract_error_no_traceback_in_json(_tok, cs_bt_http_client):
    panel = _daily_panel(["AAA"], date(2024, 1, 2), 4)
    with patch(
        "app.routes.cross_sectional_portfolio_backtest._fetch_panel_for_symbols",
        return_value=panel,
    ), patch.object(
        CrossSectionalPortfolioBacktestService,
        "run",
        side_effect=ValueError('CROSS_SECTIONAL_CONTRACT: missing weights\nTraceback (most recent call last):\n  File "x"'),
    ):
        resp = cs_bt_http_client.post(
            "/api/indicator/cross-sectional-portfolio-backtest",
            json={
                "symbolList": ["AAA"],
                "indicatorCode": "scores={s:1 for s in symbols}",
                "startDate": "2024-01-02",
                "endDate": "2024-01-05",
            },
            headers=AUTH,
        )
    assert resp.status_code == 422
    msg = resp.get_json().get("msg", "")
    assert "Traceback" not in msg
    assert 'File "' not in msg


def test_mutual_exclusive_symbol_list_and_universe_raises():
    start = date(2024, 1, 2)
    panel = _daily_panel(["A"], start, 3)
    req = {
        "panel": panel,
        "symbol_list": ["A"],
        "universe": "nq100",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=2)).isoformat(),
        "indicator_code": "scores={s:1.0 for s in symbols}; weights={s:1.0 for s in symbols}; rankings=list(symbols)",
        "trading_config": {"initial_capital": 1.0, "timeframe": "1D"},
    }
    with pytest.raises(ValueError, match="mutually exclusive"):
        CrossSectionalPortfolioBacktestService().run(req)
