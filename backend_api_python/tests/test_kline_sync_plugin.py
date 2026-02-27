"""
Tests for app/tasks/kline_sync.py — verify it delegates to scheduler_service.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestKlineSyncPlugin:
    def test_module_attributes(self):
        from app.tasks import kline_sync

        assert hasattr(kline_sync, "JOB_ID")
        assert hasattr(kline_sync, "INTERVAL_MINUTES")
        assert hasattr(kline_sync, "ENABLED")
        assert hasattr(kline_sync, "run")
        assert kline_sync.ENABLED is True  # 默认启动

    @patch("app.services.scheduler_service.run_kline_sync_once")
    def test_run_delegates_to_scheduler_service(self, mock_run_once):
        from app.tasks.kline_sync import run

        run()

        mock_run_once.assert_called_once()
