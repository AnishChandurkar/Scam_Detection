# Finfluencer Scam Detection Engine

[![Python Version](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![Transformers](https://img.shields.io/badge/Transformers-HuggingFace-orange.svg)](https://huggingface.co/transformers)

> 🌐️ English

<!--intro-start-->
## Introduction
A platform-agnostic financial scam detection engine. It takes content from social platforms, runs it through three independent checks, and outputs a weighted risk verdict: **high_risk**, **human_review**, or **cleared**.

```
content ──► normalizer ──► [Check 1: NLP] ──► [Check 2: SEBI reg] ──► [Check 3: market] ──► weighted score ──► verdict
```

For full system architecture, schemas, and check details, refer to [CLAUDE.md](CLAUDE.md).

## Features

* **Multilingual NLP Layer**: Keyword and phrase scan for pump-and-tip language (English + Hindi/Hinglish), supported by a local MuRIL transformer model (`google/muril-base-cased`) for scam classification.
* **Entity Extraction**: Custom spaCy NER pipeline supplemented by regex to extract stock tickers, person names, and SEBI registration numbers.
* **SEBI Registration Verification**: Fuzzy matches authors against SEBI's Investment Adviser (RIA) and Research Analyst (RA) registry using RapidFuzz, and verifies regex-extracted registration numbers.
* **Market Anomaly Detection**: Pulls historical daily NSE/BSE volume via yfinance and computes a Z-score baseline to flag unusual volume and price spikes.
* **Dynamic Scorer & Confidence Engine**: Renormalizes weights on skipped checks and routes low-confidence scenarios to manual human review.

## Quick start

Step 1: Setup and Installation

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone <repo-url>
   cd Scam_Detection
   ```
2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Download the spaCy language model:
   ```bash
   python -m spacy download en_core_web_sm
   ```

Step 2: Run the Demo task

5. Execute the built-in demo script:
   ```bash
   python run_demo.py
   ```
   *Note: On the first run, the MuRIL model weights (~900 MB) will be downloaded and cached by HuggingFace. Subsequent runs load from local cache.*

Step 3: Launch live connectors and scanners

6. Start the live Telegram channel listener (requires API keys in `.env`):
   ```bash
   python -m connectors.telegram_listener
   ```
7. Start the scheduled YouTube poller (requires API key in `.env`):
   ```bash
   python -m connectors.youtube_poller
   ```

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
├── requirements.txt          # Python library dependencies
├── CLAUDE.md                 # Full specification and design doc
├── AGENTS.md                 # Developer guide for AI agents
├── training_dataset_final.csv # Labelled training dataset for NLP check
├── .gitignore                # Files/folders to ignore in Git
├── .env.example              # Template for environment secrets
└── .env                      # Local environment secrets (ignored)
```

## Configuration

All tuneable parameters live in `engine/config.py` and can be overridden via environment variables or `.env`:

| Parameter | Default | Description |
|---|---|---|
| `WEIGHTS` | `nlp: 0.30, sebi: 0.40, market: 0.30` | Relative weight of each check |
| `HIGH_RISK_THRESHOLD` | `0.70` | Score ≥ this → `high_risk` |
| `REVIEW_THRESHOLD` | `0.40` | Score ≥ this → `human_review` |
| `MIN_CONFIDENCE` | `0.50` | Minimum fraction of weight that must run |
| `SEBI_MATCH_THRESHOLD` | `85` | RapidFuzz similarity score for a name match |
| `MARKET_Z_FLAG` | `2.0` | Volume Z-score above this flags an anomaly |
| `MARKET_LOOKBACK` | `40` | Calendar days of history to pull |

## The SEBI Registry CSV

The `engine/data/sebi_registered_all.csv` file ships with a **real 50-row sample** (25 RIA + 25 RA) so the engine runs out of the box. For full coverage (~1,000 RIA + ~2,000 RA), run the separate `sebi_scraper.py` (if available), then point `SEBI_CSV` in `.env` at its output.

## Important Limitations

* **Market data** from Yahoo Finance is ~15 min delayed and intraday history is limited, so Check 3 is a daily-resolution signal, not true real-time.
* **Entity extraction** of plain stock names (e.g. "RELIANCE" without `$` or `Ltd`) depends on spaCy recognising them as ORG entities — coverage is good but not exhaustive.
* **MuRIL** ships as a pretrained base model. For best accuracy, fine-tune it on a labelled dataset of scam vs. benign posts. Out of the box it provides a reasonable baseline that is supplemented by the keyword layer.
* **Scope Exclusions**: Whisper transcription (no GPU), Facebook Ad Library, and WhatsApp Business API are not implemented. The Telegram and YouTube connectors are included.
* **Decision Support**: This tool assists human review — it should not auto-accuse anyone. Treat `human_review` as the default for anything uncertain.
<!--intro-end-->
