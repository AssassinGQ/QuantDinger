"""Deployment rollout: IBKR data sufficiency guard master switch (Phase 4).

Environment variable ``QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED``:

- ``2`` / unset / empty / ``true``: **Hard-block** (default) — evaluation runs;
  insufficient outcomes block live IBKR open/add and emit user alerts.
- ``1``: **Soft-block** — evaluation runs; insufficient outcomes emit user alerts
  but do NOT block order execution (alert-only mode).
- ``0`` / ``false`` / ``no``: **Disabled** — entire sufficiency branch is skipped;
  no evaluation, no alerts, no blocking.

Operator summary: ``.planning/phases/04-hardening-and-rollout-safety/04-OPERATOR-BOUNDARIES.md``.
"""

from __future__ import annotations

import enum
import os
from typing import Optional

_ENV_KEY = "QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED"


class SufficiencyGuardMode(enum.IntEnum):
    DISABLED = 0
    SOFT_BLOCK = 1
    HARD_BLOCK = 2


_disabled_log_emitted = False


def reset_ibkr_sufficiency_guard_rollout_log_for_tests() -> None:
    """Test hook: allow repeated disabled-path log assertions in one process."""
    global _disabled_log_emitted
    _disabled_log_emitted = False


def get_ibkr_sufficiency_guard_mode() -> SufficiencyGuardMode:
    """Parse env into a tri-state guard mode."""
    raw = os.environ.get(_ENV_KEY)
    if raw is None or str(raw).strip() == "":
        return SufficiencyGuardMode.HARD_BLOCK
    v = str(raw).strip().lower()
    if v in ("false", "0", "no"):
        return SufficiencyGuardMode.DISABLED
    if v == "1":
        return SufficiencyGuardMode.SOFT_BLOCK
    return SufficiencyGuardMode.HARD_BLOCK


def is_ibkr_sufficiency_guard_enabled() -> bool:
    """Return False only when env explicitly disables the IBKR sufficiency guard."""
    return get_ibkr_sufficiency_guard_mode() != SufficiencyGuardMode.DISABLED


def maybe_log_ibkr_sufficiency_guard_disabled(logger, *, strategy_id: Optional[int]) -> None:
    """Emit at most one warning per process when the guard is disabled via env."""
    global _disabled_log_emitted
    if _disabled_log_emitted:
        return
    _disabled_log_emitted = True
    extra: dict[str, object] = {"event": "ibkr_sufficiency_guard_disabled"}
    if strategy_id is not None:
        extra["strategy_id"] = strategy_id
    logger.warning("ibkr_sufficiency_guard_disabled", extra=extra)