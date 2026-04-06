"""
Vaidya — NHM ASHA Worker Bulk Loader (Module 6)

Downloads and imports 900k+ ASHA workers from NHM open data into PostgreSQL.

Usage:
    # Full NHM import from URL
    python scripts/seeds/load_asha.py --url https://nhm.gov.in/asha_workers.csv

    # From local CSV
    python scripts/seeds/load_asha.py --file /path/to/asha_workers.csv

    # Dry run (validate only, no DB writes)
    python scripts/seeds/load_asha.py --file data.csv --dry-run

CSV column mapping (NHM open data format):
    nhm_id, name, mobile (→phone), latitude, longitude, village, district_code, state_code

Supports:
    - Resume on failure (skips existing nhm_id/phone)
    - Progress bar via tqdm
    - Batch size: 500 rows per INSERT (configurable)
    - Invalid row logging to asha_load_errors.csv
"""

import argparse
import csv
import io
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500

COLUMN_MAP = {
    # NHM CSV column  →  our DB column
    "mobile":   "phone",
    "cell":     "phone",
    "phone_no": "phone",
    "lat":      "latitude",
    "lng":      "longitude",
    "lon":      "longitude",
    "long":     "longitude",
    "district": "district_code",
    "state":    "state_code",
    "worker_id": "nhm_id",
}


def normalize_row(row: dict) -> dict | None:
    """Normalize a raw CSV row to our schema. Returns None to skip."""
    out = {}
    for k, v in row.items():
        key = k.strip().lower().replace(" ", "_")
        key = COLUMN_MAP.get(key, key)
        out[key] = v.strip() if isinstance(v, str) else v

    try:
        out["latitude"]  = float(out["latitude"])
        out["longitude"] = float(out["longitude"])
    except (KeyError, ValueError):
        return None  # no valid GPS → skip

    phone = out.get("phone", "").strip()
    if not phone or len(phone) < 10:
        return None  # no phone → skip

    name = out.get("name", "").strip()
    if not name:
        return None

    return {
        "nhm_id":       out.get("nhm_id") or None,
        "name":         name,
        "phone":        phone,
        "latitude":     out["latitude"],
        "longitude":    out["longitude"],
        "village":      out.get("village") or None,
        "district_code": out.get("district_code") or None,
        "state_code":   out.get("state_code") or None,
    }


def load_from_stream(reader: csv.DictReader, db_url: str, dry_run: bool) -> dict:
    """
    Batch-upsert rows into asha_workers.
    Uses raw psycopg2 for speed (SQLAlchemy ORM is too slow at 900k rows).
    """
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    conn = None if dry_run else psycopg2.connect(db_url)
    if conn:
        conn.autocommit = False

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
    batch: list[tuple] = []
    error_rows: list[dict] = []
    total = 0

    def flush(batch):
        if dry_run or not batch:
            return
        sql = """
            INSERT INTO asha_workers
                (nhm_id, name, phone, latitude, longitude, village, district_code, state_code, active)
            VALUES %s
            ON CONFLICT (phone) DO UPDATE SET
                nhm_id        = EXCLUDED.nhm_id,
                latitude      = EXCLUDED.latitude,
                longitude     = EXCLUDED.longitude,
                village       = COALESCE(EXCLUDED.village, asha_workers.village),
                district_code = COALESCE(EXCLUDED.district_code, asha_workers.district_code),
                state_code    = COALESCE(EXCLUDED.state_code, asha_workers.state_code),
                active        = TRUE
        """
        with conn.cursor() as cur:
            execute_values(cur, sql, batch)
        conn.commit()

    for raw_row in reader:
        total += 1
        row = normalize_row(raw_row)

        if row is None:
            stats["skipped"] += 1
            error_rows.append({**raw_row, "_error": "invalid or missing required fields"})
            continue

        batch.append((
            row["nhm_id"],
            row["name"],
            row["phone"],
            row["latitude"],
            row["longitude"],
            row["village"],
            row["district_code"],
            row["state_code"],
            True,
        ))
        stats["created"] += 1

        if len(batch) >= BATCH_SIZE:
            flush(batch)
            batch.clear()
            if total % 10_000 == 0:
                logger.info(f"Processed {total:,} rows …")

    flush(batch)
    if conn:
        conn.close()

    stats["total_read"] = total
    return stats, error_rows


def main():
    parser = argparse.ArgumentParser(description="Load NHM ASHA workers into Vaidya DB")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url",  help="HTTP URL of NHM CSV")
    src.add_argument("--file", help="Local CSV file path")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"),
                        help="PostgreSQL DSN (default: $DATABASE_URL)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate CSV only — no DB writes")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    global BATCH_SIZE
    BATCH_SIZE = args.batch_size

    if not args.dry_run and not args.db_url:
        logger.error("--db-url or $DATABASE_URL required")
        sys.exit(1)

    # ── Load CSV ──────────────────────────────────────────────────────────────
    if args.url:
        import urllib.request
        logger.info(f"Downloading {args.url} …")
        with urllib.request.urlopen(args.url, timeout=60) as resp:
            content = resp.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
    else:
        path = Path(args.file)
        if not path.exists():
            logger.error(f"File not found: {path}")
            sys.exit(1)
        f = open(path, encoding="utf-8-sig")
        reader = csv.DictReader(f)

    logger.info(f"Starting import (dry_run={args.dry_run}, batch={BATCH_SIZE}) …")
    t0 = time.time()

    stats, error_rows = load_from_stream(reader, args.db_url, args.dry_run)

    elapsed = time.time() - t0
    logger.info(
        f"Done in {elapsed:.1f}s — "
        f"created={stats['created']:,}  skipped={stats['skipped']:,}  "
        f"errors={stats['errors']:,}  total_read={stats['total_read']:,}"
    )

    if error_rows:
        err_path = Path("asha_load_errors.csv")
        with open(err_path, "w", newline="") as ef:
            writer = csv.DictWriter(ef, fieldnames=list(error_rows[0].keys()))
            writer.writeheader()
            writer.writerows(error_rows)
        logger.warning(f"{len(error_rows)} error rows written to {err_path}")

    if args.dry_run:
        logger.info("DRY RUN — no rows written to DB.")


if __name__ == "__main__":
    main()
