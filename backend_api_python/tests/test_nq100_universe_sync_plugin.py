from unittest.mock import patch

from app.tasks import nq100_universe_sync


def test_module_exports_plugin_contract():
    assert nq100_universe_sync.JOB_ID == "task_nq100_universe_sync"
    assert nq100_universe_sync.INTERVAL_MINUTES == 10080
    assert hasattr(nq100_universe_sync, "ENABLED")
    assert callable(nq100_universe_sync.run)


@patch("app.tasks.nq100_universe_sync.sync_nq100_from_csv")
def test_run_invokes_sync_nq100_from_csv_with_expected_default_paths(mock_sync):
    mock_sync.return_value = {"success": True}
    nq100_universe_sync.run()
    mock_sync.assert_called_once_with("scripts/NDX_IC.csv", "scripts/NDX_EIV.csv")
