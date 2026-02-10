import argparse
import asyncio
import os
from pathlib import Path
from typing import List

try:
    from bot.subscribers import get_active_user_ids, init_subscribers_db, mark_blocked, subscribers_count
except ModuleNotFoundError:
    from subscribers import get_active_user_ids, init_subscribers_db, mark_blocked, subscribers_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Broadcast message to bot subscribers")
    parser.add_argument("--text", type=str, default="", help="Broadcast text")
    parser.add_argument("--text-file", type=str, default="", help="Path to file with broadcast text")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of recipients (0 = all active)")
    parser.add_argument("--delay-ms", type=int, default=60, help="Delay between sends in milliseconds")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without sending")
    return parser.parse_args()


def read_broadcast_text(args: argparse.Namespace) -> str:
    file_text = ""
    if args.text_file:
        file_text = Path(args.text_file).read_text(encoding="utf-8").strip()
    text = args.text.strip() or file_text
    if not text:
        raise ValueError("Provide --text or --text-file with non-empty message")
    return text


async def send_with_retry(bot, user_id: int, text: str) -> bool:
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

    while True:
        try:
            await bot.send_message(user_id, text)
            return True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            mark_blocked(user_id)
            return False
        except TelegramBadRequest:
            mark_blocked(user_id)
            return False


async def run_broadcast(args: argparse.Namespace) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional for dry-run/local shells
        load_dotenv = None

    if load_dotenv:
        load_dotenv()

    init_subscribers_db()
    total_all = subscribers_count(active_only=False)
    total_active = subscribers_count(active_only=True)

    limit = args.limit if args.limit and args.limit > 0 else None
    recipients: List[int] = get_active_user_ids(limit=limit)
    text = read_broadcast_text(args)

    print(f"subscribers_total={total_all} active={total_active} selected={len(recipients)}")

    if args.dry_run:
        print("dry_run=true, no messages sent")
        return

    from aiogram import Bot

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    delay_s = max(0.0, args.delay_ms / 1000.0)
    sent = 0
    failed = 0

    bot = Bot(token=token)
    try:
        for index, user_id in enumerate(recipients, start=1):
            ok = await send_with_retry(bot, user_id, text)
            if ok:
                sent += 1
            else:
                failed += 1

            if delay_s > 0 and index < len(recipients):
                await asyncio.sleep(delay_s)
    finally:
        await bot.session.close()

    print(f"broadcast_done sent={sent} failed={failed}")


def main() -> None:
    args = parse_args()
    asyncio.run(run_broadcast(args))


if __name__ == "__main__":
    main()
