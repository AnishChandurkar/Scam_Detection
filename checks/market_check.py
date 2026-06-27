"""Check 3 - Market anomaly detection.

For each stock mentioned, pull recent daily price/volume from Yahoo (which mirrors
NSE/BSE) via yfinance and compute a Z-score of the latest volume against its
30-day rolling baseline. A large spike around the post time suggests a possible
pump-and-dump. Also reports the latest 1-day price move.

sub_score (0..1): based on the largest |volume z-score| across the mentioned stocks.
If no stock is mentioned, or data can't be fetched, returns available=False
(the check is skipped rather than guessed).

NOTE: Yahoo data is ~15 min delayed and intraday history is limited, so this is a
daily-resolution signal. The math here is exact; only the live fetch needs network.
"""
import config

# candidate exchange suffixes for Indian tickers on Yahoo
_SUFFIXES = [".NS", ".BO"]


def _z_from_series(volumes):
    """volumes: list of daily volumes, oldest..newest. Returns (z, latest, mean, std)."""
    if len(volumes) < 5:
        return None
    latest = volumes[-1]
    base = volumes[-(config.MARKET_ROLL_DAYS + 1):-1] or volumes[:-1]
    n = len(base)
    mean = sum(base) / n
    var = sum((v - mean) ** 2 for v in base) / n
    std = var ** 0.5
    if std == 0:
        return None
    return (latest - mean) / std, latest, mean, std


def _fetch_one(symbol):
    """Try a ticker on NSE then BSE. Returns dict or None. Needs network + yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        print("  [market] yfinance not installed; skipping.")
        return None

    for suf in _SUFFIXES:
        tkr = symbol if symbol.endswith(suf) else symbol.upper().replace(" ", "") + suf
        try:
            df = yf.Ticker(tkr).history(period=f"{config.MARKET_LOOKBACK}d", interval="1d")
        except Exception:
            df = None
        if df is None or df.empty or "Volume" not in df:
            continue
        vols = [float(v) for v in df["Volume"].tolist() if v == v]  # drop NaN
        closes = [float(c) for c in df["Close"].tolist() if c == c]
        z = _z_from_series(vols)
        if z is None:
            continue
        zval, latest, mean, std = z
        price_move = None
        if len(closes) >= 2 and closes[-2] != 0:
            price_move = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
        return {
            "ticker": tkr, "volume_z": round(zval, 2), "latest_volume": int(latest),
            "avg_volume": int(mean), "price_move_pct_1d": price_move,
        }
    return None


def _score_from_z(z):
    # |z| <= 1 -> 0 ; |z| >= 5 -> 1 ; linear between
    a = abs(z)
    return max(0.0, min(1.0, (a - 1.0) / 4.0))


def run(stocks):
    if not stocks:
        return {"name": "market", "available": False, "sub_score": None,
                "status": "no_stock_mentioned", "details": {}}

    results, best_score, best = [], 0.0, None
    for s in stocks:
        info = _fetch_one(s)
        if info is None:
            continue
        sc = _score_from_z(info["volume_z"]) if info["volume_z"] is not None else 0.0
        info["anomaly"] = abs(info["volume_z"]) >= config.MARKET_Z_FLAG
        info["sub_score"] = round(sc, 3)
        results.append(info)
        if sc >= best_score:
            best_score, best = sc, info

    if not results:
        return {"name": "market", "available": False, "sub_score": None,
                "status": "no_data", "details": {"stocks_tried": stocks}}

    return {
        "name": "market",
        "available": True,
        "sub_score": round(best_score, 3),
        "status": "anomaly" if (best and best["anomaly"]) else "normal",
        "details": {"per_stock": results, "flagged": best},
    }
