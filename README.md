# SEBI Finfluencer / Scam Detection Engine

A platform-agnostic financial scam detection engine. It takes content from social
platforms, runs it through three independent checks, and outputs a weighted risk
verdict: **high_risk**, **human_review**, or **cleared**.

```
content ──► normalizer ──► [Check 1: NLP] ──► [Check 2: SEBI reg] ──► [Check 3: market] ──► weighted score ──► verdict
```

---

## The Three Checks

1. **NLP (`engine/checks/nlp_check.py`)** — keyword/phrase scan for pump-and-tip
   language (English + Hindi/Hinglish), a **MuRIL** (`google/muril-base-cased`)
   transformer for scam-language classification, and **spaCy** NER for entity
   extraction (stock tickers, person names, SEBI registration numbers). If the
   MuRIL model fails to load it falls back to keyword-only scoring.
2. **SEBI registration (`engine/checks/sebi_check.py`)** — fuzzy-matches the author
   against SEBI's **Investment Adviser (INA…)** and **Research Analyst (INH…)**
   registries with RapidFuzz, and detects a disclosed registration number in the
   content. Unregistered → strong red flag.
3. **Market anomaly (`engine/checks/market_check.py`)** — pulls recent NSE/BSE volume
   via **yfinance** and computes a volume **Z-score** vs the 30-day baseline.
   Big spike → possible pump-and-dump.

Checks combine with configurable weights (`engine/config.py`). Skipped checks are
dropped and weights renormalized; if too little evidence ran, the verdict
defaults to **human_review** instead of guessing.

---

## Prerequisites

- **Python 3.11+**
- **pip** (or a virtual-environment tool of your choice)
- Internet access for the first run (to download MuRIL weights, spaCy model, and
  market data from Yahoo Finance)

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd Scam_Detection
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Download the spaCy language model

```bash
python -m spacy download en_core_web_sm
```

> **Note:** If you skip this step the engine will attempt to download
> `en_core_web_sm` automatically on first run.

### 5. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the keys you need:

| Variable | Required? | Description |
|---|---|---|
| `GEMINI_API_KEY` | No | No longer used by the NLP check (kept for legacy compat) |
| `YOUTUBE_DATA_V3` | Only for YouTube connector | YouTube Data API v3 key |
| `TELEGRAM_API_ID` | Only for Telegram connector | Telegram API ID |
| `TELEGRAM_API_HASH` | Only for Telegram connector | Telegram API hash |
| `SEBI_CSV` | No | Path to a full SEBI registry CSV (defaults to `engine/data/sebi_registered_all.csv`) |
| `MURIL_MODEL` | No | Override the HuggingFace model ID (defaults to `google/muril-base-cased`) |

> The **core engine** (`run_demo.py`) requires **no API keys** — MuRIL runs
> locally and the SEBI check uses the bundled CSV.

---

## Running the Engine

### Quick demo (recommended first step)

```bash
python run_demo.py
```

This runs the full pipeline on three built-in example posts (a scam tip, a
benign observation, and a registered advisor post) and prints the verdict for
each. On the **first run** MuRIL weights (~900 MB) are downloaded and cached by
HuggingFace — subsequent runs load from cache and are much faster.

Example output:

```
==============================================================================
[HIGH_RISK] risk=0.82 conf=1.0 | telegram | Pump Tips Daily
  text: '🚀 SURE SHOT TIP! Buy RELIANCE before Monday …'
  nlp   : 0.8 (muril+keywords) flags=['sure shot', 'guaranteed', 'insider', …]
  sebi  : 1.0 (unregistered) match=None @ None
  market: 0.45 (checked)
==============================================================================
```

### Live Telegram monitoring

```bash
python -m connectors.telegram_listener
```

Requires `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in `.env`. Listens to
configured channels and runs each message through the engine in real time.

### YouTube scanning

```bash
python -m connectors.youtube_poller
```

Requires `YOUTUBE_DATA_V3` in `.env`. Polls configured channels on a schedule
and analyses new video transcripts.

---

## Project Structure

```
Scam_Detection/
├── engine/
│   ├── main.py               # FastAPI app, single POST /analyse endpoint
│   ├── engine.py             # Orchestrator — runs checks in order, passes entities
│   ├── config.py             # Weights, thresholds, env-var loading
│   ├── checks/
│   │   ├── nlp_check.py      # Check 1 — MuRIL + spaCy + keyword scan
│   │   ├── sebi_check.py     # Check 2 — SEBI registry fuzzy match
│   │   └── market_check.py   # Check 3 — yfinance volume Z-score
│   ├── scoring/
│   │   └── scorer.py         # Weighted combination of check scores → verdict
│   ├── data/
│   │   ├── sebi_registered_all.csv  # 50-row sample SEBI registry
│   │   └── sebi_ria_ra.db    # SQLite database built from SEBI CSV
│   └── utils/
│       ├── normaliser.py     # Converts platform-specific data to a common dict
│       └── sebi_loader.py    # Script to download and load SEBI DB
├── connectors/
│   ├── telegram_listener.py  # Live Telegram channel listener
│   └── youtube_poller.py     # Scheduled YouTube transcript scanner
├── run_demo.py               # Quick demo on built-in example posts
├── requirements.txt
├── CLAUDE.md                 # Full specification and design doc
├── AGENTS.md                 # Developer guide for AI agents
└── .env.example              # Template for secrets
```

---

## Configuration

All tuneable parameters live in `engine/config.py`:

| Parameter | Default | Description |
|---|---|---|
| `WEIGHTS` | `nlp: 0.45, sebi: 0.30, market: 0.25` | Relative weight of each check |
| `HIGH_RISK_THRESHOLD` | `0.70` | Score ≥ this → `high_risk` |
| `REVIEW_THRESHOLD` | `0.40` | Score ≥ this → `human_review` |
| `MIN_CONFIDENCE` | `0.50` | Minimum fraction of weight that must run |
| `SEBI_MATCH_THRESHOLD` | `88` | RapidFuzz similarity score for a name match |
| `MARKET_Z_FLAG` | `2.0` | Volume Z-score above this flags an anomaly |
| `MARKET_LOOKBACK` | `40` | Calendar days of history to pull |

---

## The SEBI Registry CSV

`engine/data/sebi_registered_all.csv` ships with a **real 50-row sample** (25 RIA +
25 RA) so the engine runs out of the box. For full coverage (~1,000 RIA +
~2,000 RA), run the separate `sebi_scraper.py`, then point `SEBI_CSV` in `.env`
at its output.

---

## Important Limitations

- **Market data** from Yahoo Finance is ~15 min delayed and intraday history is
  limited, so Check 3 is a daily-resolution signal, not true real-time.
- **Entity extraction** of plain stock names (e.g. "RELIANCE" without `$` or
  `Ltd`) depends on spaCy recognising them as ORG entities — coverage is good
  but not exhaustive.
- **MuRIL** ships as a pretrained base model. For best accuracy, fine-tune it on
  a labelled dataset of scam vs. benign posts. Out of the box it provides a
  reasonable baseline that is supplemented by the keyword layer.
- **Not implemented (per scope)**: Whisper transcription (no GPU), Facebook Ad
  Library, WhatsApp Business API. The Telegram and YouTube connectors are
  included.
- This tool **assists** human review — it should not auto-accuse anyone. Treat
  `human_review` as the default for anything uncertain.

---

## Security

Keep all API keys only in `.env` (which is git-ignored). Never commit real
credentials to source control. If you suspect keys have been exposed, rotate
them immediately.
