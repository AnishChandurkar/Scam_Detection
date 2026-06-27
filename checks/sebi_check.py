"""Check 2 - Identity / SEBI registration check.

- Fuzzy-matches the author (and any 'speaker' name) against SEBI's registry of
  Investment Advisers (INA...) and Research Analysts (INH...) using RapidFuzz.
- Scans the content for a disclosed SEBI registration number (INA/INH...) and
  verifies it against the registry — the "GSTIN-style" transparency check.

sub_score (0..1): higher = more suspicious.
  - disclosed a valid reg number            -> 0.0  (transparent, verifiable)
  - name matches a registered entity        -> 0.15
  - no match (apparently UNREGISTERED)      -> 1.0  (the core SEBI red flag)
"""
import csv
import os
import re

from rapidfuzz import process, fuzz

import config

# INA/INH/INP + alphanumerics (covers INA000017523, INH300000211, INAIFSC10001)
_REGNO_RE = re.compile(r"\bIN[AHP][A-Z0-9]{6,12}\b", re.IGNORECASE)

_REGISTRY = None  # lazily loaded: {"names":[...], "by_regno":{...}, "rows":[...]}


def _load_registry():
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY
    names, by_regno, rows = [], {}, []
    path = config.SEBI_CSV
    if not os.path.exists(path):
        print(f"  [sebi] WARNING: registry CSV not found at {path}. "
              f"Run sebi_scraper.py to generate it. Treating everyone as unverified.")
        _REGISTRY = {"names": [], "by_regno": {}, "rows": []}
        return _REGISTRY
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
            nm = (row.get("name") or "").strip()
            cp = (row.get("contact_person") or "").strip()
            rn = (row.get("registration_no") or "").strip().upper()
            if nm:
                names.append(nm)
            if cp and cp.lower() != nm.lower():
                names.append(cp)
            if rn:
                by_regno[rn] = row
    _REGISTRY = {"names": names, "by_regno": by_regno, "rows": rows}
    return _REGISTRY


def _best_name_match(query, names):
    if not query or not names:
        return None, 0
    match = process.extractOne(query, names, scorer=fuzz.WRatio)
    if match is None:
        return None, 0
    return match[0], int(match[1])


def run(item, speaker_name=""):
    reg = _load_registry()
    text = item.get("text", "")
    author = item.get("author", "")

    # 1) disclosed registration number?
    disclosed = None
    for m in _REGNO_RE.finditer(text):
        rn = m.group(0).upper()
        if rn in reg["by_regno"]:
            disclosed = rn
            break
    if disclosed is None:
        # also accept any well-formed number even if not in our (possibly partial) CSV
        any_no = _REGNO_RE.search(text)
        disclosed_unverified = any_no.group(0).upper() if any_no else None
    else:
        disclosed_unverified = None

    # 2) fuzzy name match for author + speaker
    candidates = [c for c in {author, speaker_name} if c]
    best_name, best_score = None, 0
    for c in candidates:
        nm, sc = _best_name_match(c, reg["names"])
        if sc > best_score:
            best_name, best_score = nm, sc
    registered_by_name = best_score >= config.SEBI_MATCH_THRESHOLD

    # 3) decide sub_score + status
    if disclosed:
        sub_score, status = 0.0, "registered_disclosed"
    elif registered_by_name:
        sub_score, status = 0.15, "registered_name_match"
    elif not reg["names"]:
        sub_score, status = 0.5, "registry_unavailable"  # can't verify -> uncertain
    else:
        sub_score, status = 1.0, "unregistered"

    return {
        "name": "sebi",
        "sub_score": sub_score,
        "available": bool(reg["names"]) or bool(disclosed),
        "status": status,
        "details": {
            "author_checked": author,
            "speaker_checked": speaker_name,
            "best_name_match": best_name,
            "match_score": best_score,
            "disclosed_regno": disclosed,
            "disclosed_regno_unverified": disclosed_unverified,
            "registry_size": len(reg["by_regno"]),
        },
    }
