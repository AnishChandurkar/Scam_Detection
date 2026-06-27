"""Weighted scoring -> final verdict.

Combines the three checks' sub_scores using config.WEIGHTS. Checks that were
skipped (available=False / sub_score None) are dropped and the remaining weights
are renormalized. A 'confidence' = fraction of total weight that actually ran;
if confidence is low, we refuse to make a confident call and route to human review.
"""
import config


def score(check_results):
    present = {r["name"]: r for r in check_results
               if r.get("available") and r.get("sub_score") is not None}

    total_w = sum(config.WEIGHTS.values())
    used_w = sum(config.WEIGHTS[name] for name in present)
    confidence = used_w / total_w if total_w else 0.0

    if used_w == 0:
        return {
            "risk": None, "verdict": "human_review", "confidence": 0.0,
            "components": {}, "reason": "no checks could run",
        }

    risk = sum(config.WEIGHTS[name] * present[name]["sub_score"] for name in present) / used_w

    if confidence < config.MIN_CONFIDENCE:
        verdict = "human_review"  # don't over-trust thin evidence
    elif risk >= config.HIGH_RISK_THRESHOLD:
        verdict = "high_risk"
    elif risk >= config.REVIEW_THRESHOLD:
        verdict = "human_review"
    else:
        verdict = "cleared"

    return {
        "risk": round(risk, 3),
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "components": {name: present[name]["sub_score"] for name in present},
        "weights_used": {name: config.WEIGHTS[name] for name in present},
    }
