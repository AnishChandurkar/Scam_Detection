"""YouTube connector — scheduled keyword search + transcript analysis.

Searches YouTube for finance keywords (Data API v3), pulls each video's
transcript (youtube-transcript-api, incl. Hindi), normalizes, and runs the engine.
Run it on a schedule (e.g. cron). No Whisper fallback (per project scope).

    python -m connectors.youtube_poller

Set YOUTUBE_DATA_V3 in .env. Each search costs 100 quota units (10k/day free).
"""
import sys, os, json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import config
import engine
from engine.utils.normaliser import from_youtube

KEYWORDS = [
    "guaranteed stock tip",
    "intraday sure shot",
    "multibagger penny stock",
    "share market pakka tip",
]
MAX_RESULTS = 8
_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def search_videos(keyword):
    params = {
        "key": config.YOUTUBE_API_KEY, "q": keyword, "part": "snippet",
        "type": "video", "order": "date", "maxResults": MAX_RESULTS,
        "relevanceLanguage": "hi", "regionCode": "IN",
    }
    r = requests.get(_SEARCH_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("items", [])


def get_transcript(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        sys.exit("Run: pip install youtube-transcript-api")
    try:
        chunks = YouTubeTranscriptApi.get_transcript(video_id, languages=["hi", "en", "en-IN"])
        return " ".join(c["text"] for c in chunks)
    except Exception:
        return ""  # no captions; (Whisper fallback intentionally not implemented)


def main():
    if not config.YOUTUBE_API_KEY:
        sys.exit("Set YOUTUBE_DATA_V3 in .env first.")
    seen = set()
    for kw in KEYWORDS:
        try:
            items = search_videos(kw)
        except Exception as e:
            print(f"[youtube] search failed for {kw!r}: {e}")
            continue
        for v in items:
            vid = v.get("id", {}).get("videoId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            transcript = get_transcript(vid)
            item = from_youtube(v, transcript)
            if not item["text"]:
                continue
            report = engine.analyze(item)
            print("\n" + engine.pretty(report))
            if report["verdict"] in ("HIGH_RISK", "REVIEW"):
                with open("flagged.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(report, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
