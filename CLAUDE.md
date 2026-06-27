# Finfluencer Scam Detection Engine

## What This Is
A platform-agnostic financial scam detection engine. It takes any piece of financial content as text input, runs it through three sequential checks, and outputs a weighted risk score with a verdict. The engine does not handle platform ingestion — that is a separate layer. The engine only receives already-normalised text and returns a verdict.

## What The Engine Does NOT Do
- It does not scrape or ingest content from any platform
- It does not handle WhatsApp/Telegram bots
- It does not manage any UI or dashboard
- It does not send alerts or notifications

---

## Input Format
Every piece of content arrives at the engine in this normalised format:

```json
{
  "text": "full transcript or message text here",
  "platform": "telegram | whatsapp | youtube | instagram | facebook | x",
  "source_handle": "channel name or username",
  "timestamp": "ISO 8601 datetime",
  "metadata": {
    "follower_count": 0,
    "post_url": ""
  }
}
```

---

## Output Format

```json
{
  "risk_score": 0.0,
  "verdict": "HIGH_RISK | REVIEW | CLEAR",
  "signals": {
    "nlp": {
      "scam_language_detected": true,
      "flags": ["guaranteed returns", "urgency language"],
      "stock_mentioned": "IRFC",
      "entity_name": "Rajesh Stock Tips"
    },
    "sebi_check": {
      "registered": false,
      "registration_number_present": false,
      "matched_name": null
    },
    "market_anomaly": {
      "checked": true,
      "volume_zscore": 3.2,
      "price_change_pct": 12.5,
      "anomaly_detected": true
    }
  },
  "weight_breakdown": {
    "nlp_weight": 0.3,
    "sebi_weight": 0.4,
    "market_weight": 0.3,
    "final_score": 0.87
  }
}
```

---

## Three Checks — Build These In Order

### Check 1 — NLP Layer
**Goal:** Detect scam language and extract entities from the text.

- Use **MuRIL** (`google/muril-base-cased` from HuggingFace) as the base model for Hindi/Hinglish/multilingual classification
- For entity extraction (stock names, person names, IA registration numbers) use **spaCy** with a custom NER pipeline
- Scam indicator categories to detect:
  - Urgency language: "buy now", "last chance", "before Friday", "abhi lo"
  - Guaranteed returns: "100% sure", "guaranteed", "risk-free", "pakka profit"
  - Secrecy nudges: "don't tell everyone", "insider tip", "sirf tumhare liye"
  - Specific price targets with no reasoning: "will hit 500 in 3 days"
- Output: list of triggered flags + stock ticker if found + source entity name if found

### Check 2 — SEBI Registration Check
**Goal:** Cross-reference the identified entity against SEBI's registered advisor database.

- Download SEBI's RIA and RA database (available as CSV/Excel at sebi.gov.in)
- Store locally in SQLite for fast lookups
- Use **RapidFuzz** for fuzzy name matching — threshold 85% similarity score
- Also run a regex check on the raw text for SEBI registration number patterns (formats: `INA000XXXXXX` for RIAs, `INH000XXXXXX` for RAs)
- Output: registered true/false + matched name if found + registration number present true/false

### Check 3 — Market Anomaly Detection
**Goal:** Check if the mentioned stock had unusual activity around the time the content was posted.

- Use **yfinance** to pull 30 days of historical daily OHLCV data for the identified stock (NSE ticker format e.g. `IRFC.NS`)
- Calculate Z-score of the posting day's volume against 30-day rolling mean and std
- Calculate percentage price change on posting day vs previous close
- Flag as anomaly if: volume Z-score > 2.0 OR price change > 5%
- If no stock is identified in Check 1, skip this check and mark as unchecked
- Output: Z-score value + price change % + anomaly true/false

---

## Scoring Weights

| Signal | Weight |
|---|---|
| NLP scam language | 0.30 |
| SEBI unregistered | 0.40 |
| Market anomaly | 0.30 |

Scoring logic:
- Each check returns a score between 0.0 and 1.0
- Multiply each by its weight and sum for final score
- Final score thresholds:
  - >= 0.70 → HIGH_RISK
  - >= 0.40 → REVIEW
  - < 0.40 → CLEAR

---

## Tech Stack

| Component | Library |
|---|---|
| NLP model | `transformers` (HuggingFace), MuRIL |
| Entity extraction | `spaCy` |
| Fuzzy matching | `rapidfuzz` |
| Market data | `yfinance` |
| SEBI DB | `sqlite3` |
| API serving | `FastAPI` |
| Environment | Python 3.11+ |

---

## Project Structure

```
engine/
├── main.py                  # FastAPI app, single POST /analyse endpoint
├── checks/
│   ├── nlp_check.py         # Check 1
│   ├── sebi_check.py        # Check 2
│   └── market_check.py      # Check 3
├── scoring/
│   └── scorer.py            # Combines three check outputs into final verdict
├── data/
│   └── sebi_ria_ra.db       # SQLite database built from SEBI CSV
├── utils/
│   ├── normaliser.py        # Input validation and normalisation
│   └── sebi_loader.py       # Script to download and load SEBI DB
├── requirements.txt
└── CLAUDE.md
```

---

## API

Single endpoint:

```
POST /analyse
Content-Type: application/json
Body: normalised input object (see Input Format above)
Returns: verdict object (see Output Format above)
```

---

## Important Notes

- All three checks must run independently and not depend on each other's output
- If a check fails (e.g. yfinance cannot find the stock), it should return a neutral score of 0.0 for that check and mark it as unchecked — do not crash the pipeline
- Keep each check in its own file, scorer.py only imports results from checks
- The engine should process one input at a time — concurrency is handled upstream by the task queue, not inside the engine
- Hindi and Hinglish text written in Roman script (e.g. "yeh stock bahut badhega") must be handled — MuRIL supports this natively
- Do not hardcode SEBI database path — use environment variables
