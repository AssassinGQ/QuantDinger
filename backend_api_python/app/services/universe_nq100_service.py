"""
NQ100 universe: point-in-time membership reads (qd_nq100_membership).

Change history for audit lives in qd_nq100_change_events; this module only
answers “which symbols were in the index on calendar date D?” using interval
semantics on membership rows (source / scraped_at on rows are set at ingest).
"""
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from app.services.nq100_csv_ingest_service import (
    import_nq100_csv_bundle,
    try_enrich_weights_from_qqq,
)
from app.utils.logger import get_logger
from app.utils import db

__all__ = ["get_constituents_as_of", "get_eiv_as_of", "sync_nq100_from_csv"]

logger = get_logger(__name__)

# PostgreSQL treats NULL valid_to as “still active” via COALESCE to infinity::date.
_PIT_SQL = """
    SELECT symbol
    FROM qd_nq100_membership
    WHERE %s::date BETWEEN valid_from AND COALESCE(valid_to, 'infinity'::date)
    ORDER BY symbol
"""


def get_constituents_as_of(as_of_date: date) -> List[str]:
    """
    Return sorted unique symbols that were NQ100 constituents on as_of_date.

    Semantics: as_of_date lies in [valid_from, COALESCE(valid_to, infinity)].

    Symbols are normalized to uppercase strings for stable comparisons across
    callers (ingest should store consistent casing; this layer still normalizes).
    """
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_PIT_SQL, (as_of_date,))
        rows = cursor.fetchall()
    # De-duplicate in case of overlapping rows; sort for deterministic output.
    symbols = sorted({str(row[0]).strip().upper() for row in rows})
    return symbols


def get_eiv_as_of(as_of_date: date) -> Optional[Dict[str, object]]:
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT trade_date, index_symbol, eod_index_value, source
            FROM qd_nq100_index_eiv
            WHERE trade_date = %s
            """,
            (as_of_date,),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        "date": row[0],
        "index_symbol": row[1],
        "eod_index_value": float(row[2]) if row[2] is not None else None,
        "source": row[3],
    }


def sync_nq100_from_csv(
    ic_csv_path: str = "scripts/NDX_IC.csv",
    eiv_csv_path: str = "scripts/NDX_EIV.csv",
) -> Dict[str, object]:
    summary: Dict[str, object] = {
        "success": True,
        "ic_csv_path": ic_csv_path,
        "eiv_csv_path": eiv_csv_path,
    }
    bundle_summary = import_nq100_csv_bundle(ic_csv_path, eiv_csv_path)
    summary.update(bundle_summary)
    try:
        qqq_summary = try_enrich_weights_from_qqq(str(Path("scripts") / "qqq_holdings.csv"))
        summary.update(qqq_summary)
    except Exception as exc:
        logger.warning("QQQ weight enrichment raised unexpectedly (non-blocking): %s", exc)
        summary["qqq_weight_enrich_status"] = "failed_non_blocking"
    if summary.get("qqq_weight_enrich_status") != "success":
        summary["qqq_weight_enrich_status"] = "failed_non_blocking"
    return summary

