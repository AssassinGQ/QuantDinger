"""Deployment rollout: IBKR data sufficiency guard master switch (Phase 4).

Environment variable ``QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED``:

- **Default ON:** When unset or empty, the sufficiency guard behaves as after Phase 2
  (evaluation runs; insufficient outcomes may block live IBKR open/add).
- **Explicit OFF:** Case-insensitive ``false``, ``0``, or ``no`` disables the guard.

**Guard / alert coupling (R-03):** Disabling the guard makes ``SignalExecutor`` skip the
**entire** sufficiency branch for qualifying live IBKR open/add signals. That means **no**
sufficiency-driven open block **and** **no** Phase 3 insufficient user-channel alerts that
fire only after a sufficiency block — there is no separate "alerts without blocking" mode.

Incident-only: turning the guard off removes protection against trading on thin or
unknown-schedule data; use only for break-glass recovery.

Operator summary: ``.planning/phases/04-hardening-and-rollout-safety/04-OPERATOR-BOUNDARIES.md``.
"""

from __future__ import annotations

import os
from typing import Optional

_ENV_KEY = "QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED"

_disabled_log_emitted = False


def reset_ibkr_sufficiency_guard_rollout_log_for_tests() -> None:
    """Test hook: allow repeated disabled-path log assertions in one process."""
    global _disabled_log_emitted
    _disabled_log_emitted = False


def is_ibkr_sufficiency_guard_enabled() -> bool:
    """Return False when env explicitly disables the IBKR sufficiency guard."""
    raw = os.environ.get(_ENV_KEY)
    if raw is None or str(raw).strip() == "":
        return True
    v = str(raw).strip().lower()
    if v in ("false", "0", "no"):
        return False
    return True


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
