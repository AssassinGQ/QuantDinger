"""
Tests for the plugin-style scheduled task registry (register / unregister / get_all_jobs_status).
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Reset the module-level scheduler singleton between tests."""
    import app.services.scheduler_service as mod
    original = mod._scheduler
    mod._scheduler = None
    yield
    if mod._scheduler is not None:
        try:
            mod._scheduler.shutdown(wait=False)
        except Exception:
            pass
    mod._scheduler = original


class TestRegisterScheduledJob:
    def test_register_new_job(self):
        from app.services.scheduler_service import register_scheduled_job, get_scheduler

        called = []

        def dummy():
            called.append(1)

        result = register_scheduled_job("test_job_1", dummy, interval_minutes=60)
        assert result is True

        sched = get_scheduler()
        job = sched.get_job("test_job_1")
        assert job is not None

    def test_register_duplicate_replace(self):
        from app.services.scheduler_service import register_scheduled_job, get_scheduler

        register_scheduled_job("test_dup", lambda: None, interval_minutes=60)
        result = register_scheduled_job("test_dup", lambda: None, interval_minutes=30, replace=True)
        assert result is True

    def test_register_duplicate_no_replace(self):
        from app.services.scheduler_service import register_scheduled_job

        register_scheduled_job("test_norep", lambda: None, interval_minutes=60)
        result = register_scheduled_job("test_norep", lambda: None, interval_minutes=30, replace=False)
        assert result is False


class TestUnregisterScheduledJob:
    def test_unregister_existing(self):
        from app.services.scheduler_service import (
            register_scheduled_job, unregister_scheduled_job, get_scheduler,
        )

        register_scheduled_job("test_unreg", lambda: None, interval_minutes=60)
        result = unregister_scheduled_job("test_unreg")
        assert result is True

        sched = get_scheduler()
        assert sched.get_job("test_unreg") is None

    def test_unregister_nonexistent(self):
        from app.services.scheduler_service import unregister_scheduled_job

        result = unregister_scheduled_job("nonexistent_job")
        assert result is False


class TestGetAllJobsStatus:
    def test_returns_registered_jobs(self):
        from app.services.scheduler_service import (
            register_scheduled_job, get_all_jobs_status,
        )

        register_scheduled_job("status_a", lambda: None, interval_minutes=10)
        register_scheduled_job("status_b", lambda: None, interval_minutes=20)

        statuses = get_all_jobs_status()
        ids = {s["job_id"] for s in statuses}
        assert "status_a" in ids
        assert "status_b" in ids


class TestRegisterAllTasks:
    @patch("app.tasks.regime_switch.ENABLED", True)
    @patch("app.tasks.kline_sync.ENABLED", False)
    @patch("app.services.scheduler_service.register_scheduled_job")
    def test_registers_regime_switch_only(self, mock_reg):
        from app.tasks import register_all_tasks
        register_all_tasks()

        job_ids = [call.args[0] for call in mock_reg.call_args_list]
        assert "task_regime_switch" in job_ids
        assert "task_kline_sync" not in job_ids

    @patch("app.tasks.regime_switch.ENABLED", False)
    @patch("app.tasks.kline_sync.ENABLED", False)
    @patch("app.services.scheduler_service.register_scheduled_job")
    def test_registers_nothing_when_disabled(self, mock_reg):
        from app.tasks import register_all_tasks
        register_all_tasks()
        mock_reg.assert_not_called()
