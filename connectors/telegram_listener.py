"""Telegram connector — real-time listener (Telethon).

Listens to the public channels/groups you list, normalizes each new message,
runs it through the engine, and prints/saves the verdict.

Run on your own machine (first run asks for your phone + a login code):
    python -m connectors.telegram_listener

Set TELEGRAM_API_ID / TELEGRAM_API_HASH in .env. Add channels to CHANNELS below.
"""
import asyncio
import json
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import config
import engine
from engine.utils.normaliser import from_telegram

# Public channels/groups to monitor (usernames or t.me links or numeric ids).
CHANNELS = [
    # "somefinancetipschannel",
    # "anotherstockgroup",
]


async def main():
    try:
        from telethon import TelegramClient, events
    except ImportError:
        sys.exit("Telethon not installed. Run: pip install telethon")

    if not (config.TELEGRAM_API_ID and config.TELEGRAM_API_HASH):
        sys.exit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first.")
    if not CHANNELS:
        sys.exit("Add at least one channel to CHANNELS in connectors/telegram_listener.py")

    client = TelegramClient("sebi_engine_session", int(config.TELEGRAM_API_ID), config.TELEGRAM_API_HASH)

    @client.on(events.NewMessage(chats=CHANNELS))
    async def handler(event):
        item = from_telegram(event)
        if not item["text"]:
            return
        report = engine.analyze(item)
        print("\n" + engine.pretty(report))
        # append high-risk / review items to a JSONL file for follow-up
        if report["verdict"] in ("HIGH_RISK", "REVIEW"):
            with open("flagged.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(report, ensure_ascii=False) + "\n")

    print(f"Listening on {len(CHANNELS)} channel(s)... Ctrl+C to stop.")
    await client.start()
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
