"""CSV ingest for NQ100 IC and EIV datasets with idempotent writes."""

from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Tuple

from app.utils import db
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_date(value: str) -> date:
    v = (value or "").strip()
    if len(v) == 7:
        return datetime.strptime(v, "%Y-%m").date().replace(day=1)
    return datetime.strptime(v, "%Y-%m-%d").date()


def import_ic_csv(csv_path: str) -> Dict[str, int]:
    rows_read = 0
    inserted = 0
    seen_keys: set[Tuple[str, date, str]] = set()

    with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            for row in reader:
                rows_read += 1
                index_symbol = (row.get("index_symbol") or "").strip().upper()
                trade_date = _parse_date(row.get("date") or "")
                component_symbol = (row.get("component_symbol") or "").strip().upper()
                key = (index_symbol, trade_date, component_symbol)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                source = f"{index_symbol}|NDX_IC.csv"
                cursor.execute(
                    """
                    INSERT INTO qd_nq100_membership(symbol, valid_from, valid_to, source, scraped_at)
                    SELECT %s, %s, %s, %s, NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM qd_nq100_membership
                        WHERE symbol = %s AND valid_from = %s AND source = %s
                    )
                    """,
                    (
                        component_symbol,
                        trade_date,
                        trade_date,
                        source,
                        component_symbol,
                        trade_date,
                        source,
                    ),
                )
                inserted += max(cursor.rowcount, 0)

                cursor.execute(
                    """
                    INSERT INTO qd_nq100_ic_raw(
                        index_symbol, trade_date, component_symbol, source, raw_payload, scraped_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (index_symbol, trade_date, component_symbol)
                    DO UPDATE SET
                        raw_payload = EXCLUDED.raw_payload,
                        source = EXCLUDED.source,
                        updated_at = NOW()
                    """,
                    (index_symbol, trade_date, component_symbol, "NDX_IC.csv", dict(row)),
                )
            conn.commit()

    return {
        "ic_rows_read": rows_read,
        "ic_rows_inserted": inserted,
        "ic_rows_upserted_or_skipped": rows_read - inserted,
    }


def import_eiv_csv(csv_path: str) -> Dict[str, int]:
    rows_read = 0
    upserted = 0

    with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            for row in reader:
                rows_read += 1
                trade_date = _parse_date(row.get("date") or "")
                index_symbol = (row.get("index_symbol") or "").strip().upper()
                eod_index_value = Decimal((row.get("eod_index_value") or "0").strip())

                cursor.execute(
                    """
                    INSERT INTO qd_nq100_index_eiv(
                        trade_date, index_symbol, eod_index_value, source, raw_payload, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (trade_date)
                    DO UPDATE SET
                        index_symbol = EXCLUDED.index_symbol,
                        eod_index_value = EXCLUDED.eod_index_value,
                        source = EXCLUDED.source,
                        raw_payload = EXCLUDED.raw_payload,
                        updated_at = NOW()
                    """,
                    (trade_date, index_symbol, eod_index_value, "NDX_EIV.csv", dict(row)),
                )
                upserted += 1
            conn.commit()

    return {
        "eiv_rows_read": rows_read,
        "eiv_rows_upserted": upserted,
    }


def import_nq100_csv_bundle(ic_path: str, eiv_path: str) -> Dict[str, int]:
    ic_summary = import_ic_csv(ic_path)
    eiv_summary = import_eiv_csv(eiv_path)
    return {
        "ic_rows_read": ic_summary["ic_rows_read"],
        "ic_rows_inserted": ic_summary["ic_rows_inserted"],
        "ic_rows_upserted_or_skipped": ic_summary["ic_rows_upserted_or_skipped"],
        "eiv_rows_read": eiv_summary["eiv_rows_read"],
        "eiv_rows_upserted": eiv_summary["eiv_rows_upserted"],
    }


def try_enrich_weights_from_qqq(qqq_csv_path: str = "scripts/qqq_holdings.csv") -> Dict[str, int | str]:
    """
    Best-effort QQQ weight enrichment.
    Any parse/read/runtime failure is captured and logged; no exception is raised.
    """
    try:
        rows_read = 0
        rows_upserted = 0
        with Path(qqq_csv_path).open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                for row in reader:
                    rows_read += 1
                    symbol = (row.get("symbol") or "").strip().upper()
                    if not symbol:
                        continue
                    weight_raw = (row.get("weight_pct") or "").strip()
                    if not weight_raw:
                        continue
                    try:
                        weight = Decimal(weight_raw)
                    except Exception:
                        logger.warning("Invalid QQQ weight for symbol=%s: %s", symbol, weight_raw)
                        continue
                    cursor.execute(
                        """
                        UPDATE qd_nq100_membership
                        SET weight = %s, updated_at = NOW()
                        WHERE symbol = %s
                        """,
                        (weight, symbol),
                    )
                    rows_upserted += max(cursor.rowcount, 0)
                conn.commit()
        return {
            "qqq_rows_read": rows_read,
            "qqq_rows_updated": rows_upserted,
            "qqq_weight_enrich_status": "success",
        }
    except Exception as exc:
        logger.warning("QQQ weight enrichment failed (non-blocking): %s", exc)
        return {
            "qqq_rows_read": 0,
            "qqq_rows_updated": 0,
            "qqq_weight_enrich_status": "failed_non_blocking",
        }
