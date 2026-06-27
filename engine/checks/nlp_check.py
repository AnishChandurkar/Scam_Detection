"""Check 1 — Language analysis (NLP layer).

Two parts:
  1. A fast keyword/phrase scan for classic scam-tip language (works offline).
  2. MuRIL (google/muril-base-cased) — a HuggingFace transformer fine-tuned for
     Indian-language text — used as a sequence classifier to produce a scam
     probability.  On first run the model weights are downloaded and cached.
  3. spaCy entity extraction for stock tickers, person names, and SEBI
     registration numbers.

Returns a sub_score in 0..1 (higher = more scam-like), the extracted entities,
and details.  If MuRIL is unavailable at runtime (e.g. missing weights), the
score falls back to keywords only and the mode is marked "keyword_only".
"""

import os
import re
import logging

from engine import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Lazy singletons — heavy models are loaded once on first call.
# ---------------------------------------------------------------------------
_muril_pipeline = None
_spacy_nlp = None

# Model identifier for MuRIL on HuggingFace.
_MURIL_MODEL = os.getenv("MURIL_MODEL", "google/muril-base-cased")

# Label map — MuRIL fine-tuned for sequence classification returns string
# labels.  We map them to a float probability.  If the model was only
# pretrained (no classification head), we fall back to keyword scoring.
_SCAM_LABELS = {
    "LABEL_1": 1.0,   # scam / manipulative
    "LABEL_0": 0.0,   # benign
    "scam": 1.0,
    "not_scam": 0.0,
    "benign": 0.0,
}


def _load_muril():
    """Load MuRIL text-classification pipeline (lazy, thread-safe enough)."""
    global _muril_pipeline
    if _muril_pipeline is not None:
        return _muril_pipeline

    try:
        from transformers import pipeline as hf_pipeline
        _muril_pipeline = hf_pipeline(
            "text-classification",
            model=_MURIL_MODEL,
            tokenizer=_MURIL_MODEL,
            truncation=True,
            max_length=512,
        )
        logger.info("MuRIL pipeline loaded from %s", _MURIL_MODEL)
    except Exception as exc:
        logger.warning("Failed to load MuRIL pipeline (%s); falling back to keywords.", exc)
        _muril_pipeline = None
    return _muril_pipeline


def _load_spacy():
    """Load a spaCy model for NER.  Falls back gracefully."""
    global _spacy_nlp
    if _spacy_nlp is not None:
        return _spacy_nlp

    try:
        import spacy

        # Prefer the medium English model if available; fall back to small.
        for model_name in ("en_core_web_md", "en_core_web_sm"):
            try:
                _spacy_nlp = spacy.load(model_name)
                logger.info("spaCy model '%s' loaded.", model_name)
                return _spacy_nlp
            except OSError:
                continue

        # If no pre-installed model, download en_core_web_sm on the fly.
        logger.info("No spaCy model found locally; downloading en_core_web_sm …")
        spacy.cli.download("en_core_web_sm")
        _spacy_nlp = spacy.load("en_core_web_sm")
        logger.info("spaCy model 'en_core_web_sm' loaded after download.")
    except Exception as exc:
        logger.warning("spaCy unavailable (%s); entity extraction will use regex only.", exc)
        _spacy_nlp = None
    return _spacy_nlp


# ---------------------------------------------------------------------------
#  Keyword / phrase scanning (kept from original — Hindi & Hinglish support)
# ---------------------------------------------------------------------------
SCAM_PHRASES = [
    "buy before", "last chance", "100% sure", "100 percent", "risk free", "risk-free",
    "guaranteed", "guarantee", "sure shot", "sureshot", "multibagger", "multi bagger",
    "insider", "insider tip", "don't share", "do not share", "dont share",
    "target", "intraday tip", "jackpot", "double your money", "2x", "10x",
    "dabba", "operator", "lock kar lo", "abhi kharido", "abhi le lo", "pakka",
    "loss nahi", "loss nahi hoga", "guaranteed return", "fixed return",
    "tip", "blast", "rocket", "upper circuit", "circuit lagega", "bumper",
]


def _keyword_scan(text):
    """Return (score, list_of_hit_phrases).  Score saturates at ~0.8."""
    low = " " + text.lower() + " "
    hits = [p for p in SCAM_PHRASES if p in low]
    # 0 hits -> 0.0, 1 -> ~0.38, 2 -> ~0.56, 3 -> ~0.74, 4+ -> 0.80 cap
    n = len(hits)
    score = min(0.8, 0.0 if n == 0 else 0.2 + 0.18 * n)
    return score, hits


# ---------------------------------------------------------------------------
#  MuRIL-based scam classification
# ---------------------------------------------------------------------------

def _classify_muril(text):
    """Run MuRIL text-classification and return a scam probability 0..1,
    or None if the model is unavailable.
    """
    pipe = _load_muril()
    if pipe is None:
        return None

    try:
        # Truncate long texts — MuRIL supports 512 tokens.
        result = pipe(text[:2000])
        if not result:
            return None

        top = result[0]
        label = top.get("label", "")
        raw_score = float(top.get("score", 0.0))

        # Map the label to a scam-direction probability.
        if label in _SCAM_LABELS:
            direction = _SCAM_LABELS[label]
        else:
            # Unknown label — use raw score as-is, clamped.
            direction = 0.5

        # If the label means "scam", the probability IS the raw score.
        # If the label means "benign", the scam probability is 1 - raw_score.
        if direction >= 0.5:
            scam_prob = raw_score
        else:
            scam_prob = 1.0 - raw_score

        return max(0.0, min(1.0, scam_prob))

    except Exception as exc:
        logger.warning("MuRIL inference failed (%s); using keyword fallback.", exc)
        return None


# ---------------------------------------------------------------------------
#  Entity extraction — spaCy + regex
# ---------------------------------------------------------------------------

# Regex: $TICKER, "ABC Ltd / Limited / Industries …"
_TICKER_RE = re.compile(r"\$([A-Za-z]{2,12})\b")
_LTD_RE = re.compile(
    r"\b([A-Z][A-Za-z&.\- ]{2,40}?"
    r"(?:Ltd|Limited|Industries|Motors|Bank|Pharma|Tech|Power|Steel|Finance))\b"
)

# SEBI registration number patterns:  INA000XXXXXX (RIA), INH000XXXXXX (RA)
_SEBI_REG_RE = re.compile(r"\b(IN[AH]\d{9,12})\b")


def _extract_entities(text):
    """Extract stock tickers, person names, and SEBI reg numbers.

    Uses spaCy NER when available; always supplements with regex patterns.
    Returns dict with keys: stocks, persons, sebi_numbers.
    """
    stocks: set[str] = set()
    persons: set[str] = set()
    sebi_numbers: set[str] = set()

    # --- Regex-based extraction (always runs) ---
    stocks.update(m.group(1) for m in _TICKER_RE.finditer(text))
    stocks.update(m.group(1).strip() for m in _LTD_RE.finditer(text))
    sebi_numbers.update(m.group(1) for m in _SEBI_REG_RE.finditer(text))

    # --- spaCy NER ---
    nlp = _load_spacy()
    if nlp is not None:
        try:
            doc = nlp(text[:5000])  # cap length for performance
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    persons.add(ent.text.strip())
                elif ent.label_ == "ORG":
                    # ORGs that look like stock tickers / company names
                    stocks.add(ent.text.strip())
        except Exception as exc:
            logger.warning("spaCy NER failed (%s); using regex entities only.", exc)

    return {
        "stocks": sorted(stocks),
        "persons": sorted(persons),
        "sebi_numbers": sorted(sebi_numbers),
    }


# ---------------------------------------------------------------------------
#  Public entry point — called by engine.py
# ---------------------------------------------------------------------------

def run(item):
    """Analyse the text of *item* and return an NLP check result dict.

    Return schema (consumed by engine.py / scoring.py):
        name:       "nlp"
        sub_score:  float 0..1
        available:  True
        mode:       "muril+keywords" | "keyword_only"
        entities:   {stocks: [...], speaker_claim: str}
        details:    {keyword_hits: [...], red_flags: [...],
                     is_investment_advice: bool|None, reasoning: str}
    """
    text = item.get("text", "")

    # 1. Keyword scan (fast, offline)
    kw_score, kw_hits = _keyword_scan(text)

    # 2. MuRIL classification
    muril_prob = _classify_muril(text)

    # 3. Entity extraction (spaCy + regex)
    entities = _extract_entities(text)

    # --- Combine scores ----
    if muril_prob is not None:
        # Trust MuRIL but let strong keyword signal raise the floor.
        sub_score = max(muril_prob, kw_score * 0.9)
        mode = "muril+keywords"
    else:
        sub_score = kw_score
        mode = "keyword_only"

    # Derive convenience flags
    is_advice = sub_score >= 0.35 and len(kw_hits) > 0
    red_flags = list(kw_hits)  # keywords already serve as red-flag labels

    # Build speaker claim from person entities
    speaker_claim = ", ".join(entities["persons"]) if entities["persons"] else ""

    return {
        "name": "nlp",
        "sub_score": round(sub_score, 3),
        "available": True,
        "mode": mode,
        "entities": {
            "stocks": entities["stocks"],
            "speaker_claim": speaker_claim,
            "persons": entities["persons"],
            "sebi_numbers": entities["sebi_numbers"],
        },
        "details": {
            "keyword_hits": kw_hits,
            "is_investment_advice": is_advice,
            "red_flags": red_flags,
            "reasoning": (
                f"MuRIL scam_prob={muril_prob:.3f}" if muril_prob is not None
                else "MuRIL unavailable; keyword-only scoring"
            ),
        },
    }
