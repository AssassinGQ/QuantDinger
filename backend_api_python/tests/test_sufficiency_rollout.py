"""Tests for ``QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED`` rollout helper."""

from app.config import sufficiency_rollout
from app.config.sufficiency_rollout import SufficiencyGuardMode


def test_guard_enabled_by_default(monkeypatch):
    monkeypatch.delenv("QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED", raising=False)
    assert sufficiency_rollout.is_ibkr_sufficiency_guard_enabled() is True
    assert sufficiency_rollout.get_ibkr_sufficiency_guard_mode() == SufficiencyGuardMode.HARD_BLOCK


def test_guard_disabled_falsey_strings(monkeypatch):
    for v in ("false", "FALSE", "0", "no", "No"):
        monkeypatch.setenv("QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED", v)
        assert sufficiency_rollout.is_ibkr_sufficiency_guard_enabled() is False
        assert sufficiency_rollout.get_ibkr_sufficiency_guard_mode() == SufficiencyGuardMode.DISABLED


def test_guard_soft_block_mode(monkeypatch):
    monkeypatch.setenv("QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED", "1")
    assert sufficiency_rollout.is_ibkr_sufficiency_guard_enabled() is True
    assert sufficiency_rollout.get_ibkr_sufficiency_guard_mode() == SufficiencyGuardMode.SOFT_BLOCK


def test_guard_hard_block_explicit(monkeypatch):
    for v in ("2", "true", "TRUE", "yes", "Yes"):
        monkeypatch.setenv("QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED", v)
        assert sufficiency_rollout.is_ibkr_sufficiency_guard_enabled() is True
        assert sufficiency_rollout.get_ibkr_sufficiency_guard_mode() == SufficiencyGuardMode.HARD_BLOCK