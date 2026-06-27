"""Check 2 - Identity / SEBI registration check.

- Fuzzy-matches the author (and any 'speaker' name) against SEBI's registry of
  Investment Advisers (INA...) and Research Analysts (INH...) using RapidFuzz.
- Scans the content for a disclosed SEBI registration number (INA/INH...) and
  verifies it against the registry — the "GSTIN-style" transparency check.

Data source: SQLite database at data/sebi_ria_ra.db (built from CSV by
utils/sebi_loader.py; auto-created on first run if the CSV exists).

sub_score (0..1): higher = more suspicious.
  - disclosed a valid reg number            -> 0.0  (transparent, verifiable)
  - name matches a registered entity        -> 0.15
  - no match (apparently UNREGISTERED)      -> 1.0  (the core SEBI red flag)
"""
import os
import re
import sqlite3

from rapidfuzz import process, fuzz

from engine import config
from engine.utils.sebi_loader import ensure_db

# INA/INH/INP + alphanumerics (covers INA000017523, INH300000211, INAIFSC10001)
_REGNO_RE = re.compile(r"\bIN[AHP][A-Z0-9]{6,12}\b", re.IGNORECASE)

_CONN = None  # lazily opened SQLite connection


def _get_connection():
    """Return a (cached) read-only SQLite connection to the SEBI DB."""
    global _CONN
    if _CONN is not None:
        return _CONN

    db_path = ensure_db()

    if not os.path.exists(db_path):
        # Neither CSV nor DB available
        return None

    _CONN = sqlite3.connect(db_path)
    _CONN.row_factory = sqlite3.Row
    return _CONN


def _load_names(conn):
    """Fetch all searchable names from the DB for fuzzy matching."""
    if conn is None:
        return []
    cur = conn.execute(
        "SELECT DISTINCT name FROM registrants WHERE name != '' "
        "UNION "
        "SELECT DISTINCT contact_person FROM registrants "
        "WHERE contact_person != '' AND LOWER(contact_person) NOT IN "
        "(SELECT LOWER(name) FROM registrants WHERE name != '')"
    )
    return [row[0] for row in cur.fetchall()]


def _lookup_regno(conn, regno: str):
    """Check if a registration number exists in the DB. Returns the row or None."""
    if conn is None:
        return None
    cur = conn.execute(
        "SELECT * FROM registrants WHERE registration_no = ?",
        (regno.upper(),),
    )
    return cur.fetchone()


def _count_registrants(conn) -> int:
    """Return the total number of distinct registration numbers."""
    if conn is None:
        return 0
    cur = conn.execute(
        "SELECT COUNT(DISTINCT registration_no) FROM registrants "
        "WHERE registration_no != ''"
    )
    return cur.fetchone()[0]


def _best_name_match(query, names):
    if not query or not names:
        return None, 0
    match = process.extractOne(query, names, scorer=fuzz.WRatio)
    if match is None:
        return None, 0
    return match[0], int(match[1])


def run(item, speaker_name=""):
    conn = _get_connection()
    text = item.get("text", "")
    author = item.get("author", "")

    # 1) disclosed registration number?
    disclosed = None
    for m in _REGNO_RE.finditer(text):
        rn = m.group(0).upper()
        if _lookup_regno(conn, rn) is not None:
            disclosed = rn
            break
    if disclosed is None:
        # also accept any well-formed number even if not in our (possibly partial) DB
        any_no = _REGNO_RE.search(text)
        disclosed_unverified = any_no.group(0).upper() if any_no else None
    else:
        disclosed_unverified = None

    # 2) fuzzy name match for author + speaker
    names = _load_names(conn)
    candidates = [c for c in {author, speaker_name} if c]
    best_name, best_score = None, 0
    for c in candidates:
        nm, sc = _best_name_match(c, names)
        if sc > best_score:
            best_name, best_score = nm, sc
    registered_by_name = best_score >= config.SEBI_MATCH_THRESHOLD

    # 3) decide sub_score + status
    if disclosed:
        sub_score, status = 0.0, "registered_disclosed"
    elif registered_by_name:
        sub_score, status = 0.15, "registered_name_match"
    elif not names:
        sub_score, status = 0.5, "registry_unavailable"  # can't verify -> uncertain
    else:
        sub_score, status = 1.0, "unregistered"

    registry_size = _count_registrants(conn)

    return {
        "name": "sebi",
        "sub_score": sub_score,
        "available": bool(names) or bool(disclosed),
        "status": status,
        "details": {
            "author_checked": author,
            "speaker_checked": speaker_name,
            "best_name_match": best_name,
            "match_score": best_score,
            "disclosed_regno": disclosed,
            "disclosed_regno_unverified": disclosed_unverified,
            "registry_size": registry_size,
        },
    }
