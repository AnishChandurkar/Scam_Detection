"""Utility to load SEBI registry CSV into a SQLite database.

Reads data/sebi_registered_all.csv and materializes it into a SQLite DB
at data/sebi_ria_ra.db so that the SEBI check can query it directly
instead of parsing CSV on every startup.

Usage:
    python -m engine.utils.sebi_loader          # one-off load / refresh
    from engine.utils.sebi_loader import ensure_db   # called at runtime
"""
import csv
import os
import sqlite3

from engine import config

_DB_PATH = config.SEBI_DB
_CSV_PATH = config.SEBI_CSV

_SCHEMA = """
CREATE TABLE IF NOT EXISTS registrants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT,
    name            TEXT,
    registration_no TEXT,
    email           TEXT,
    telephone       TEXT,
    fax             TEXT,
    address         TEXT,
    contact_person  TEXT,
    correspondence_address TEXT,
    validity        TEXT
);

CREATE INDEX IF NOT EXISTS idx_reg_no   ON registrants(registration_no);
CREATE INDEX IF NOT EXISTS idx_name     ON registrants(name);
CREATE INDEX IF NOT EXISTS idx_contact  ON registrants(contact_person);
"""


def _csv_rows(csv_path: str):
    """Yield dicts from the SEBI CSV."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield row


def build_db(csv_path: str | None = None, db_path: str | None = None) -> str:
    """(Re-)create the SQLite database from the CSV.

    Returns the path to the created DB file.
    """
    csv_path = csv_path or _CSV_PATH
    db_path = db_path or _DB_PATH

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"SEBI CSV not found at {csv_path}. "
            "Run sebi_scraper.py first to generate it."
        )

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    # Remove stale DB so we get a clean load
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)

    insert_sql = """
        INSERT INTO registrants
            (category, name, registration_no, email, telephone, fax,
             address, contact_person, correspondence_address, validity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    count = 0
    for row in _csv_rows(csv_path):
        conn.execute(insert_sql, (
            row.get("category", ""),
            row.get("name", ""),
            (row.get("registration_no") or "").strip().upper(),
            row.get("email", ""),
            row.get("telephone", ""),
            row.get("fax", ""),
            row.get("address", ""),
            row.get("contact_person", ""),
            row.get("correspondence_address", ""),
            row.get("validity", ""),
        ))
        count += 1

    conn.commit()
    conn.close()
    print(f"[sebi_loader] Loaded {count} registrants from CSV -> {db_path}")
    return db_path


def ensure_db(db_path: str | None = None, csv_path: str | None = None) -> str:
    """Return the path to the SQLite DB, building it from CSV if missing."""
    db_path = db_path or _DB_PATH
    csv_path = csv_path or _CSV_PATH

    if not os.path.exists(db_path):
        # Auto-build from CSV if the DB doesn't exist yet
        if os.path.exists(csv_path):
            return build_db(csv_path, db_path)
        else:
            # Neither DB nor CSV — caller must handle gracefully
            return db_path

    return db_path


# ── CLI entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    build_db()
