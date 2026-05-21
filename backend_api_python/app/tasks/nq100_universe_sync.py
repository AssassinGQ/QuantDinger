"""
NQ100 universe sync plugin.
"""

from app.services.universe_nq100_service import sync_nq100_from_csv
from app.utils.logger import get_logger

logger = get_logger(__name__)

JOB_ID = "task_nq100_universe_sync"
INTERVAL_MINUTES = 10080
ENABLED = True


def run() -> None:
    logger.info("[nq100_universe_sync] start")
    summary = sync_nq100_from_csv("scripts/NDX_IC.csv", "scripts/NDX_EIV.csv")
    logger.info("[nq100_universe_sync] done summary=%s", summary)
