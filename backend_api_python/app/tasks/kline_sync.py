"""
kline_sync 插件 — 委托 scheduler_service 现有 K 线同步逻辑。

首版不自动注册 APScheduler job（避免与现有 /api/scheduler/start 管理的 kline job 双跑）。
仅提供 JOB_ID / INTERVAL_MINUTES / run()，供手动测试或后续替换。
"""

from app.utils.logger import get_logger

logger = get_logger(__name__)

JOB_ID = "task_kline_sync"
INTERVAL_MINUTES = 400
ENABLED = False  # 首版不自动注册


def run() -> None:
    """执行一次完整 K 线同步（委托 scheduler_service）。"""
    logger.info("[kline_sync] delegating to scheduler_service.run_kline_sync_once()")
    from app.services.scheduler_service import run_kline_sync_once
    run_kline_sync_once()
    logger.info("[kline_sync] done")
