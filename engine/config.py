"""Central configuration. Secrets are read from environment variables / .env —
never hard-code real keys in source. See .env.example."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass  # python-dotenv optional; env vars still work without it

# --- API credentials (from environment) ---
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # stable free-tier model (Q2 2026)
YOUTUBE_API_KEY   = os.getenv("YOUTUBE_DATA_V3")
TELEGRAM_API_ID   = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

# --- Data ---
# CSV produced by sebi_scraper.py. A small real sample ships in data/.
SEBI_CSV = os.getenv("SEBI_CSV", os.path.join(os.path.dirname(__file__), "data", "sebi_registered_all.csv"))
# SQLite DB built from the CSV by utils/sebi_loader.py (auto-created on first run).
SEBI_DB  = os.getenv("SEBI_DB",  os.path.join(os.path.dirname(__file__), "data", "sebi_ria_ra.db"))

# --- Scoring ---
# Weight of each check when all three are available. Renormalized if some are skipped.
WEIGHTS = {"nlp": 0.30, "sebi": 0.40, "market": 0.30}

# risk >= HIGH_RISK -> "HIGH_RISK"; >= REVIEW -> "REVIEW"; else "CLEAR"
HIGH_RISK_THRESHOLD = 0.70
REVIEW_THRESHOLD     = 0.40

# If less than this fraction of total weight actually ran, never auto-declare
# "high_risk" or "cleared" — fall back to "human_review" (don't over-trust thin evidence).
MIN_CONFIDENCE = 0.50

# --- Check 2 (SEBI) ---
SEBI_MATCH_THRESHOLD = 85   # RapidFuzz score (0-100) to count a name as "registered"

# --- Check 3 (market) ---
MARKET_Z_FLAG    = 2.0      # |volume z-score| above this is anomalous
MARKET_PRICE_FLAG = 5.0     # |price move %| above this is anomalous
MARKET_LOOKBACK  = 40       # calendar-ish days of history to pull
MARKET_ROLL_DAYS = 30       # rolling window for the volume baseline
