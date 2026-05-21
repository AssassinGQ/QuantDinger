"""Phase 21 correctness gates for cross-sectional execution semantics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from app.strategies.runners.cross_sectional_runner import (
    CrossSectionalRunner,
    ExecutionPolicy,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "phase21"


def _load_json(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _mock_db_for_delisting():
    """Helper to mock database connection for DelistingPolicyFilter."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # No remove events

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_db = MagicMock()
    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=mock_conn)
    mock_context.__exit__ = MagicMock(return_value=False)
    mock_db.get_db_connection.return_value = mock_context

    return mock_db


def _build_runner() -> CrossSectionalRunner:
    return CrossSectionalRunner(data_handler=MagicMock(), signal_executor=MagicMock())


def test_no_lookahead_gate():
    prices = pd.read_csv(FIXTURE_DIR / "prices.csv")
    row = prices.iloc[0].to_dict()
    signal = {
        "symbol": row["symbol"],
        "type": "open_long",
        "signal_date": row["signal_date"],
        "execution_date": row["execution_date"],
    }
    runner = _build_runner()
    # Mock database for DelistingPolicyFilter
    mock_db = _mock_db_for_delisting()
    with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
        accepted, _meta = runner._filter_phase21_signals(  # pylint: disable=protected-access
            [signal],
            ExecutionPolicy(fallback_mode="strict"),
            {"market_rows": {row["symbol"]: row}},
        )
    assert accepted
    assert accepted[0]["execution_date"] > accepted[0]["signal_date"]


def test_fallback_policy():
    prices = pd.read_csv(FIXTURE_DIR / "prices_with_invalid_open.csv")
    row = prices.iloc[0].to_dict()
    signal = {
        "symbol": row["symbol"],
        "type": "open_long",
        "signal_date": row["signal_date"],
        "execution_date": row["execution_date"],
    }
    runner = _build_runner()
    # Mock database for DelistingPolicyFilter
    mock_db = _mock_db_for_delisting()
    with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
        accepted, meta = runner._filter_phase21_signals(  # pylint: disable=protected-access
            [signal],
            ExecutionPolicy(fallback_mode="close"),
            {"market_rows": {row["symbol"]: row}},
        )
    assert accepted[0]["price_source"] == "close"
    assert meta["fallback_count_total"] == 1
    assert meta["fallback_rate"] == 1.0


def test_untradable_filters():
    timeline = pd.read_csv(FIXTURE_DIR / "tradability_timeline.csv")
    row = timeline[timeline["symbol"] == "BBB"].iloc[0].to_dict()
    signal = {
        "symbol": "BBB",
        "type": "open_long",
        "signal_date": row["signal_date"],
        "execution_date": row["execution_date"],
    }
    runner = _build_runner()
    # Mock database for DelistingPolicyFilter
    mock_db = _mock_db_for_delisting()
    with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
        accepted, meta = runner._filter_phase21_signals(  # pylint: disable=protected-access
            [signal],
            ExecutionPolicy(),
            {
                "tradability": {"BBB": "UNTRADABLE"},
                "market_rows": {"BBB": {"next_open": 200.0, "adv20_usd": 5_000_000}},
            },
        )
    assert accepted == []
    assert meta["execution_logs"][0]["status"] == "skipped_untradable_buy_cash_kept"


def test_cash_substitution_no_replacement():
    runner = _build_runner()
    signals = [
        {"symbol": "BBB", "type": "open_long", "signal_date": "2024-02-01", "execution_date": "2024-02-02"},
        {"symbol": "AAA", "type": "open_long", "signal_date": "2024-02-01", "execution_date": "2024-02-02"},
    ]
    # Mock database for DelistingPolicyFilter
    mock_db = _mock_db_for_delisting()
    with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
        accepted, meta = runner._filter_phase21_signals(  # pylint: disable=protected-access
            signals,
            ExecutionPolicy(),
            {
                "tradability": {"BBB": "UNTRADABLE", "AAA": "TRADABLE"},
                "market_rows": {
                    "AAA": {"next_open": 101.0, "adv20_usd": 3_000_000},
                    "BBB": {"next_open": 98.0, "adv20_usd": 3_000_000},
                },
            },
        )
    assert len(accepted) == 1
    assert accepted[0]["symbol"] == "AAA"
    assert meta["execution_logs"][0]["status"] == "skipped_untradable_buy_cash_kept"


def test_sell_hold_and_resume_cycle():
    runner = _build_runner()
    sell_signal = {
        "symbol": "CCC",
        "type": "close_long",
        "signal_date": "2024-02-01",
        "execution_date": "2024-02-02",
    }
    # Mock database for DelistingPolicyFilter
    mock_db = _mock_db_for_delisting()
    with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
        accepted, meta = runner._filter_phase21_signals(  # pylint: disable=protected-access
            [sell_signal],
            ExecutionPolicy(),
            {"tradability": {"CCC": "UNTRADABLE"}, "market_rows": {"CCC": {"next_open": 45.0, "adv20_usd": 2_000_000}}},
        )
    assert accepted == []
    assert meta["execution_logs"][0]["status"] == "skipped_untradable_sell_hold_position"


def test_cash_mna_forced_exit():
    mna_events = _load_json("mna_cash_events.json")
    runner = _build_runner()
    signal = {
        "symbol": "DDD",
        "type": "close_long",
        "signal_date": "2024-02-01",
        "execution_date": "2024-02-02",
    }
    # Mock database for DelistingPolicyFilter
    mock_db = _mock_db_for_delisting()
    with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
        accepted, meta = runner._filter_phase21_signals(  # pylint: disable=protected-access
            [signal],
            ExecutionPolicy(),
            {"market_rows": {"DDD": {"next_open": 100.0, "adv20_usd": 9_000_000}}, "cash_mna": mna_events},
        )
    assert accepted[0]["type"] == "forced_cash_exit"
    assert meta["execution_logs"][0]["status"] == "forced_cash_exit"


def test_ic_effective_date_shift():
    row = pd.read_csv(FIXTURE_DIR / "ic_effective_dates.csv").iloc[0].to_dict()
    runner = _build_runner()
    signal = {
        "symbol": "AAA",
        "type": "open_long",
        "signal_date": row["signal_date"],
        "execution_date": row["execution_date"],
    }
    # Mock database for DelistingPolicyFilter and _query_change_events
    mock_db = _mock_db_for_delisting()
    with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
        with patch("app.strategies.runners.cross_sectional_runner.db", mock_db):
            accepted, _meta = runner._filter_phase21_signals(  # pylint: disable=protected-access
                [signal],
                ExecutionPolicy(),
                {
                    "ic_effective_dates": [row["execution_date"]],
                    "market_rows": {"AAA": {"next_open": 111.0, "adv20_usd": 4_000_000}},
                },
            )
    assert accepted[0]["execution_date"] == row["expected_shifted_execution_date"]


def test_determinism_gate():
    prices = pd.read_csv(FIXTURE_DIR / "prices.csv")
    signal = {
        "symbol": "AAA",
        "type": "open_long",
        "signal_date": prices.iloc[1]["signal_date"],
        "execution_date": prices.iloc[1]["execution_date"],
    }
    runner = _build_runner()

    def run_once() -> str:
        # Mock database for DelistingPolicyFilter
        mock_db = _mock_db_for_delisting()
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            accepted, meta = runner._filter_phase21_signals(  # pylint: disable=protected-access
                [signal],
                ExecutionPolicy(fallback_mode="strict"),
                {"market_rows": {"AAA": prices.iloc[1].to_dict()}},
            )
        payload = json.dumps({"accepted": accepted, "logs": meta["execution_logs"]}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    assert run_once() == run_once()
