"""Engine orchestrator.

analyze(item) runs the three checks in order, passing entities between them
(NLP extracts the stocks -> market check uses them; NLP extracts the speaker
-> SEBI check uses them), then produces the final weighted verdict.
"""
from engine.checks import nlp_check, sebi_check, market_check
from engine.scoring import scorer


def analyze(item):
    # Check 1: language + entity extraction
    nlp = nlp_check.run(item)
    stocks = nlp["entities"].get("stocks", [])
    speaker = nlp["entities"].get("speaker_claim", "")

    # Check 2: SEBI registration (author + any speaker name from NLP)
    sebi = sebi_check.run(item, speaker_name=speaker if isinstance(speaker, str) else "")

    # Check 3: market anomaly on the mentioned stocks
    market = market_check.run(stocks)

    verdict = scorer.score([nlp, sebi, market])

    return {
        "item": {k: item[k] for k in ("platform", "author", "source", "timestamp", "url")},
        "text_preview": (item.get("text", "")[:200]),
        "verdict": verdict["verdict"],
        "risk_score": verdict["risk_score"],
        "confidence": verdict["confidence"],
        "signals": verdict["signals"],
        "weight_breakdown": verdict["weight_breakdown"],
        "checks": {"nlp": nlp, "sebi": sebi, "market": market},
    }


def pretty(report):
    v = report["verdict"]
    r = report["risk_score"]
    line = f"[{v}] risk_score={r} conf={report['confidence']} | {report['item']['platform']} | {report['item']['author']}"
    nlp, sebi, market = report["checks"]["nlp"], report["checks"]["sebi"], report["checks"]["market"]
    parts = [
        line,
        f"  text: {report['text_preview']!r}",
        f"  nlp   : {nlp['sub_score']} ({nlp['mode']}) flags={nlp['details'].get('red_flags') or nlp['details'].get('keyword_hits')}",
        f"  sebi  : {sebi['sub_score']} ({sebi['status']}) match={sebi['details'].get('best_name_match')} @ {sebi['details'].get('match_score')}",
        f"  market: {market['sub_score']} ({market['status']})",
    ]
    return "\n".join(parts)
