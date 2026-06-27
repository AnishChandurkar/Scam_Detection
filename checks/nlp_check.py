"""Check 1 - Language analysis (NLP layer).

Two parts:
  1. A fast keyword/phrase scan for classic scam-tip language (works offline, no key).
  2. A Gemini call that classifies scam likelihood AND extracts entities
     (which stock, who is making the claim). Runs only if GEMINI_API_KEY is set.

Returns a sub_score in 0..1 (higher = more scam-like), the extracted entities,
and details. If Gemini is unavailable, the score falls back to keywords only
and the mode is marked "keyword_only" — it never fabricates a model score.
"""
import json
import re
import requests

import config

# Classic pump/advice red-flag phrases, incl. common Hindi/Hinglish variants.
SCAM_PHRASES = [
    "buy before", "last chance", "100% sure", "100 percent", "risk free", "risk-free",
    "guaranteed", "guarantee", "sure shot", "sureshot", "multibagger", "multi bagger",
    "insider", "insider tip", "don't share", "do not share", "dont share",
    "target", "intraday tip", "jackpot", "double your money", "2x", "10x",
    "dabba", "operator", "lock kar lo", "abhi kharido", "abhi le lo", "pakka",
    "loss nahi", "loss nahi hoga", "guaranteed return", "fixed return",
    "tip", "blast", "rocket", "upper circuit", "circuit lagega", "bumper",
]

# crude ticker-ish patterns: $ABC, "ABC Ltd", all-caps tokens of length 3-12
_TICKER_RE = re.compile(r"\$([A-Za-z]{2,12})\b")
_LTD_RE = re.compile(r"\b([A-Z][A-Za-z&.\- ]{2,40}?(?:Ltd|Limited|Industries|Motors|Bank|Pharma|Tech|Power|Steel|Finance))\b")

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_PROMPT = """You are a securities-fraud screening assistant for the Indian market (SEBI context).
Analyse the SOCIAL MEDIA CONTENT below. Respond with ONLY a JSON object, no prose, with keys:
- scam_probability: number 0..1 (likelihood this is a manipulative/pump or unregistered-advice post)
- is_investment_advice: boolean (does it give a buy/sell/target recommendation?)
- stocks: array of strings (stock names or NSE/BSE tickers explicitly mentioned)
- speaker_claim: string (what the author claims about themselves / the tip, short)
- red_flags: array of short strings
- reasoning: one short sentence

CONTENT:
\"\"\"{content}\"\"\""""


def _keyword_scan(text):
    low = " " + text.lower() + " "
    hits = [p for p in SCAM_PHRASES if p in low]
    # score saturates: 0 hits -> 0.0, 1 -> ~0.35, 2 -> ~0.55, 3 -> ~0.7, 4+ -> ~0.8 cap
    n = len(hits)
    score = min(0.8, 0.0 if n == 0 else 0.2 + 0.18 * n)
    return score, hits


def _regex_entities(text):
    stocks = set(m.group(1) for m in _TICKER_RE.finditer(text))
    stocks |= set(m.group(1).strip() for m in _LTD_RE.finditer(text))
    return sorted(stocks)


def _call_gemini(text):
    """Return parsed dict from Gemini, or None on any failure."""
    if not config.GEMINI_API_KEY:
        return None
    url = _GEMINI_URL.format(model=config.GEMINI_MODEL)
    body = {
        "contents": [{"parts": [{"text": _PROMPT.format(content=text[:6000])}]}],
        "generationConfig": {"temperature": 0, "response_mime_type": "application/json"},
    }
    try:
        r = requests.post(
            url,
            headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw)
    except Exception as e:
        print(f"  [nlp] Gemini call failed ({e}); using keyword-only.")
        return None


def run(item):
    text = item.get("text", "")
    kw_score, kw_hits = _keyword_scan(text)
    entities = _regex_entities(text)
    gemini = _call_gemini(text)

    if gemini is not None:
        try:
            g_prob = float(gemini.get("scam_probability", 0.0))
        except (TypeError, ValueError):
            g_prob = 0.0
        g_prob = max(0.0, min(1.0, g_prob))
        # combine: trust the model but let strong keyword signal raise the floor
        sub_score = max(g_prob, kw_score * 0.9)
        stocks = sorted(set(entities) | set(gemini.get("stocks", []) or []))
        mode = "gemini+keywords"
    else:
        sub_score = kw_score
        stocks = entities
        gemini = {}
        mode = "keyword_only"

    return {
        "name": "nlp",
        "sub_score": round(sub_score, 3),
        "available": True,
        "mode": mode,
        "entities": {
            "stocks": stocks,
            "speaker_claim": gemini.get("speaker_claim", ""),
        },
        "details": {
            "keyword_hits": kw_hits,
            "is_investment_advice": gemini.get("is_investment_advice"),
            "red_flags": gemini.get("red_flags", []),
            "reasoning": gemini.get("reasoning", ""),
        },
    }
