"""Normaliser — every platform's content becomes the same dict before analysis.

Common item schema:
    {
      "text": str,          # the message / transcript / caption
      "platform": str,      # "telegram" | "youtube" | ...
      "author": str,        # channel name / handle / speaker
      "source": str,        # channel id, video id, group name
      "timestamp": str,     # ISO-8601 UTC
      "url": str,
      "extra": dict,        # platform-specific extras (forward chain, view count...)
    }
"""
from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize(text, platform, author="", source="", timestamp=None, url="", extra=None):
    return {
        "text": (text or "").strip(),
        "platform": platform,
        "author": (author or "").strip(),
        "source": (source or "").strip(),
        "timestamp": timestamp or _now_iso(),
        "url": url or "",
        "extra": extra or {},
    }


def from_telegram(event):
    """Telethon NewMessage event -> normalized item."""
    msg = event.message
    chat = getattr(event, "chat", None)
    author = getattr(chat, "title", None) or getattr(chat, "username", None) or str(getattr(event, "chat_id", ""))
    fwd = msg.forward
    extra = {}
    if fwd is not None:
        extra["forwarded"] = True
        extra["forward_from"] = str(getattr(fwd, "from_name", "") or getattr(fwd, "from_id", ""))
    return normalize(
        text=msg.message or "",
        platform="telegram",
        author=author,
        source=str(getattr(event, "chat_id", "")),
        timestamp=(msg.date.isoformat() if msg.date else None),
        extra=extra,
    )


def from_youtube(video_meta, transcript_text):
    """YouTube Data API video item + transcript -> normalized item."""
    sn = video_meta.get("snippet", {})
    vid = (video_meta.get("id", {}) or {}).get("videoId") or video_meta.get("id", "")
    return normalize(
        text=transcript_text or sn.get("description", ""),
        platform="youtube",
        author=sn.get("channelTitle", ""),
        source=vid,
        timestamp=sn.get("publishedAt"),
        url=f"https://www.youtube.com/watch?v={vid}",
        extra={"title": sn.get("title", "")},
    )
