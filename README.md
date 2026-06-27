# SEBI Finfluencer / Scam Detection Engine

A working implementation of the engine from the SEBI proposal. It takes content
from social platforms, runs it through three checks, and outputs a risk verdict:
**high_risk**, **human_review**, or **cleared**.

```
content ──► normalizer ──► [Check 1: NLP] ──► [Check 2: SEBI reg] ──► [Check 3: market] ──► weighted score ──► verdict
```

## The three checks

1. **NLP (`checks/nlp_check.py`)** — a real keyword/phrase scan for pump-and-tip
   language (English + Hindi/Hinglish), plus a **Gemini** call that scores scam
   likelihood and extracts entities (which stock, who is claiming). No Gemini key →
   it falls back to keyword-only and says so. *(MuRIL was dropped — see notes.)*
2. **SEBI registration (`checks/sebi_check.py`)** — fuzzy-matches the author against
   SEBI's **Investment Adviser (INA…)** and **Research Analyst (INH…)** registries
   with RapidFuzz, and detects a disclosed registration number in the content
   (the "GSTIN-style" check). Unregistered → strong red flag.
3. **Market anomaly (`checks/market_check.py`)** — pulls recent NSE/BSE volume via
   **yfinance** and computes a volume **Z-score** vs the 30-day baseline. Big spike →
   possible pump-and-dump.

The checks combine with configurable weights (`config.py`). Skipped checks are
dropped and weights renormalized; if too little evidence ran, the verdict defaults
to **human_review** instead of guessing.

## Setup (run on your own machine)

```bash
pip install -r requirements.txt
playwright install chromium      # only needed for the SEBI scraper
cp .env.example .env             # then fill in your keys
```

## Run

```bash
python run_demo.py                       # full pipeline on example inputs
python -m connectors.telegram_listener   # live Telegram monitoring
python -m connectors.youtube_poller      # scheduled YouTube scanning
```

## The SEBI registry CSV

`data/sebi_registered_all.csv` ships with a **real 50-row sample** (25 RIA + 25 RA)
so the engine runs out of the box. For full coverage (~1,000 RIA + ~2,000 RA), run
the separate `sebi_scraper.py`, then point `SEBI_CSV` at its output.

## Important limitations (read these)

- **Could not be run as a full live service inside the build sandbox** — its network
  blocks `sebi.gov.in`, Gemini, Yahoo, Telegram and YouTube. The code is real and
  tested offline (scoring, keyword layer, SEBI matching, Z-score math); the live API
  calls work when you run it on your own machine with the keys set.
- **NLP model**: this uses **Gemini zero-shot**, not a fine-tuned MuRIL. That avoids
  needing a labelled dataset to start. To improve accuracy later, log flagged items,
  hand-correct a sample, and fine-tune a model on that — a standard human-in-the-loop loop.
- **Market data** from Yahoo is ~15 min delayed and intraday history is limited, so
  Check 3 is a daily-resolution signal, not true real-time.
- **Entity extraction** of plain stock names (e.g. "RELIANCE" with no `$`/`Ltd`) relies
  on the Gemini layer; with no key, only `$TICKER`/"X Ltd" patterns are caught.
- **Not implemented (per scope)**: Whisper transcription (no GPU), Facebook Ad Library,
  WhatsApp Business API. The Telegram and YouTube connectors are included.
- This tool **assists** review; it should not auto-accuse anyone. Treat `human_review`
  as the default for anything uncertain.

## Security

Rotate the Telegram/YouTube/Gemini keys you shared earlier — treat them as exposed.
Keep real keys only in `.env` (which is git-ignored by convention), never in source.
