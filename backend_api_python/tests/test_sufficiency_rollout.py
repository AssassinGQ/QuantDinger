"""Tests for ``QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED`` rollout helper."""

from app.config import sufficiency_rollout


def test_guard_enabled_by_default(monkeypatch):
    monkeypatch.delenv("QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED", raising=False)
    assert sufficiency_rollout.is_ibkr_sufficiency_guard_enabled() is True


def test_guard_disabled_falsey_strings(monkeypatch):
    for v in ("false", "FALSE", "0", "no", "No"):
        monkeypatch.setenv("QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED", v)
        assert sufficiency_rollout.is_ibkr_sufficiency_guard_enabled() is False
