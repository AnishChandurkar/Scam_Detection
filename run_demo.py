"""End-to-end demo — runs the full pipeline (normalize -> 3 checks -> verdict)
on a few EXAMPLE inputs so you can see the engine work without any platform login.

The checks run for REAL:
  - SEBI check: always real (uses the local CSV in data/).
  - NLP check : keyword layer is real; the Gemini layer runs if GEMINI_API_KEY is set.
  - Market check: runs if yfinance can reach the internet AND a stock is detected.
Whatever can't run is reported as skipped — nothing is faked.

    python run_demo.py
"""
from engine.utils.normaliser import normalize
import engine

EXAMPLES = [
    normalize(
        text=("🚀 SURE SHOT TIP! Buy RELIANCE before Monday, target 3200 guaranteed! "
              "100% sure profit, insider info. Don't share this with everyone. Lock kar lo!"),
        platform="telegram", author="Pump Tips Daily", source="-100123",
    ),
    normalize(
        text=("Quarterly results look steady. I track TCS for the long term; "
              "no recommendation, just sharing my notes."),
        platform="telegram", author="360 ONE Investment Adviser and Trustee Services Limited",
    ),
    normalize(
        text=("Educational thread on position sizing. SEBI RIA INA000017523. "
              "Nothing here is a buy/sell call."),
        platform="youtube", author="1 Finance Private Limited",
    ),
]


def main():
    for item in EXAMPLES:
        report = engine.analyze(item)
        print("\n" + "=" * 78)
        print(engine.pretty(report))
    print("\n" + "=" * 78)
    print("Done. (MuRIL runs locally — no API key needed for NLP; "
          "internet access enables the live market check.)")


if __name__ == "__main__":
    main()
