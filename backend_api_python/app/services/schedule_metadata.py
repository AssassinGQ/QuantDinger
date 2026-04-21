"""Single source of truth for IBKR schedule diagnostic string literals (Phase 4)."""

from __future__ import annotations

from typing import Final

# Values serialized on ``IBKRScheduleSnapshot.schedule_failure_reason`` / diagnostics.
SCHEDULE_FAILURE_TIMEZONE_ID_UNRESOLVED: Final[str] = "timezone_id_unresolved"
SCHEDULE_FAILURE_EMPTY_OR_UNPARSABLE: Final[str] = "empty_or_unparsable_schedule"