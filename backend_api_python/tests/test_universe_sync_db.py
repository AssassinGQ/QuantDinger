from unittest.mock import patch

from app.services.universe_nq100_service import sync_nq100_from_csv


@patch("app.services.universe_nq100_service.try_enrich_weights_from_qqq")
@patch("app.services.universe_nq100_service.import_nq100_csv_bundle")
def test_sync_nq100_from_csv_calls_ic_and_eiv_importers(mock_import_bundle, mock_enrich):
    mock_import_bundle.return_value = {
        "ic_rows_read": 10,
        "ic_rows_inserted": 8,
        "ic_rows_upserted_or_skipped": 2,
        "eiv_rows_read": 5,
        "eiv_rows_upserted": 5,
    }
    mock_enrich.return_value = {"qqq_weight_enrich_status": "success", "qqq_rows_updated": 3}

    summary = sync_nq100_from_csv("scripts/NDX_IC.csv", "scripts/NDX_EIV.csv")

    mock_import_bundle.assert_called_once_with("scripts/NDX_IC.csv", "scripts/NDX_EIV.csv")
    mock_enrich.assert_called_once()
    assert summary["ic_rows_inserted"] == 8
    assert summary["eiv_rows_upserted"] == 5


@patch("app.services.universe_nq100_service.logger")
@patch("app.services.universe_nq100_service.try_enrich_weights_from_qqq", side_effect=RuntimeError("qqq fail"))
@patch("app.services.universe_nq100_service.import_nq100_csv_bundle")
def test_sync_nq100_from_csv_qqq_failure_logs_warning_but_returns_success(
    mock_import_bundle, _mock_enrich, mock_logger
):
    mock_import_bundle.return_value = {
        "ic_rows_read": 1,
        "ic_rows_inserted": 1,
        "ic_rows_upserted_or_skipped": 0,
        "eiv_rows_read": 1,
        "eiv_rows_upserted": 1,
    }

    summary = sync_nq100_from_csv("scripts/NDX_IC.csv", "scripts/NDX_EIV.csv")

    assert summary["success"] is True
    assert summary["qqq_weight_enrich_status"] == "failed_non_blocking"
    mock_logger.warning.assert_called()


@patch("app.services.universe_nq100_service.try_enrich_weights_from_qqq")
@patch("app.services.universe_nq100_service.import_nq100_csv_bundle")
def test_sync_nq100_from_csv_is_idempotent_for_duplicate_runs(mock_import_bundle, mock_enrich):
    mock_import_bundle.side_effect = [
        {
            "ic_rows_read": 2,
            "ic_rows_inserted": 2,
            "ic_rows_upserted_or_skipped": 0,
            "eiv_rows_read": 2,
            "eiv_rows_upserted": 2,
        },
        {
            "ic_rows_read": 2,
            "ic_rows_inserted": 0,
            "ic_rows_upserted_or_skipped": 2,
            "eiv_rows_read": 2,
            "eiv_rows_upserted": 2,
        },
    ]
    mock_enrich.return_value = {"qqq_weight_enrich_status": "success", "qqq_rows_updated": 0}

    first = sync_nq100_from_csv("scripts/NDX_IC.csv", "scripts/NDX_EIV.csv")
    second = sync_nq100_from_csv("scripts/NDX_IC.csv", "scripts/NDX_EIV.csv")

    assert first["ic_rows_inserted"] == 2
    assert second["ic_rows_inserted"] == 0
    assert second["ic_rows_upserted_or_skipped"] == 2
