"""Weighted scoring -> final verdict.

Combines the three checks' sub_scores using config.WEIGHTS. Checks that were
skipped (available=False / sub_score None) are dropped and the remaining weights
are renormalized. A 'confidence' = fraction of total weight that actually ran;
if confidence is low, we refuse to make a confident call and route to human review.

Output conforms to the schema defined in CLAUDE.md:
  risk_score, verdict (HIGH_RISK | REVIEW | CLEAR), signals {nlp, sebi_check,
  market_anomaly}, weight_breakdown.
"""
from engine import config


# Signal mappers — translate each check's internal dict into the public schema

def _map_nlp_signal(result):
    """Build signals.nlp from the nlp_check result dict."""
    sub = result.get("sub_score", 0.0) or 0.0
    details = result.get("details", {})
    entities = result.get("entities", {})

    flags = details.get("keyword_hits", []) or details.get("red_flags", [])
    stocks = entities.get("stocks", [])

    return {
        "scam_language_detected": sub >= 0.35 and len(flags) > 0,
        "flags": list(flags),
        "stock_mentioned": stocks[0] if stocks else "",
    }


def _map_sebi_signal(result):
    """Build signals.sebi_check from the sebi_check result dict."""
    details = result.get("details", {})
    status = result.get("status", "")

    registered = status in ("registered_disclosed", "registered_name_match")
    regno_present = bool(details.get("disclosed_regno"))

    return {
        "registered": registered,
        "registration_number_present": regno_present,
    }


def _map_market_signal(result):
    """Build signals.market_anomaly from the market_check result dict."""
    details = result.get("details", {})
    flagged = details.get("flagged") or {}

    volume_z = flagged.get("volume_z", 0.0) if flagged else 0.0
    anomaly = flagged.get("anomaly", False) if flagged else False

    return {
        "volume_zscore": float(volume_z) if volume_z is not None else 0.0,
        "anomaly_detected": bool(anomaly),
    }


# Main scorer

def score(check_results):
    """Combine check outputs into the final verdict payload.

    Parameters
    ----------
    check_results : list[dict]
        Each dict has at minimum: name, sub_score, available.

    Returns
    -------
    dict  matching the Output Format in CLAUDE.md.
    """
    # Index results by check name for easy lookup.
    by_name = {r["name"]: r for r in check_results}

    # Filter to checks that actually ran.
    present = {r["name"]: r for r in check_results
               if r.get("available") and r.get("sub_score") is not None}

    total_w = sum(config.WEIGHTS.values())
    used_w = sum(config.WEIGHTS[name] for name in present)
    confidence = used_w / total_w if total_w else 0.0

    # Edge case: nothing ran
    if used_w == 0:
        return {
            "risk_score": None,
            "verdict": "REVIEW",
            "confidence": 0.0,
            "signals": {
                "nlp": _map_nlp_signal(by_name.get("nlp", {})),
                "sebi_check": _map_sebi_signal(by_name.get("sebi", {})),
                "market_anomaly": _map_market_signal(by_name.get("market", {})),
            },
            "weight_breakdown": {
                "nlp_weight": config.WEIGHTS["nlp"],
                "sebi_weight": config.WEIGHTS["sebi"],
                "market_weight": config.WEIGHTS["market"],
                "final_score": 0.0,
            },
            "reason": "no checks could run",
        }

    # Compute risk score
    risk = sum(
        config.WEIGHTS[name] * present[name]["sub_score"]
        for name in present
    ) / used_w

    # Determine verdict
    if confidence < config.MIN_CONFIDENCE:
        verdict = "REVIEW"          # don't over-trust thin evidence
    elif risk >= config.HIGH_RISK_THRESHOLD:
        verdict = "HIGH_RISK"
    elif risk >= config.REVIEW_THRESHOLD:
        verdict = "REVIEW"
    else:
        verdict = "CLEAR"

    # Build signals
    signals = {
        "nlp": _map_nlp_signal(by_name.get("nlp", {})),
        "sebi_check": _map_sebi_signal(by_name.get("sebi", {})),
        "market_anomaly": _map_market_signal(by_name.get("market", {})),
    }

    # Build weight breakdown
    weight_breakdown = {
        "nlp_weight": config.WEIGHTS["nlp"],
        "sebi_weight": config.WEIGHTS["sebi"],
        "market_weight": config.WEIGHTS["market"],
        "final_score": round(risk, 3),
    }

    return {
        "risk_score": round(risk, 3),
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "signals": signals,
        "weight_breakdown": weight_breakdown,
    }
