import asyncio
import os
from typing import Optional, Set

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, User, WebAppInfo
from dotenv import load_dotenv

try:
    from bot.subscribers import (
        init_subscribers_db,
        new_subscribers_count,
        subscribers_count,
        subscribers_recent_count,
        upsert_subscriber,
    )
except ModuleNotFoundError:
    from subscribers import (
        init_subscribers_db,
        new_subscribers_count,
        subscribers_count,
        subscribers_recent_count,
        upsert_subscriber,
    )

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


def normalize_username(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().lstrip("@").lower()
    return normalized or None


def parse_admin_ids() -> Set[int]:
    raw_values = ",".join(
        value
        for value in [os.getenv("BOT_ADMIN_IDS", ""), os.getenv("DEV_ADMIN_IDS", "")]
        if value
    )
    admin_ids: Set[int] = set()
    for chunk in raw_values.split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            admin_ids.add(int(item))
        except ValueError:
            continue
    return admin_ids


def parse_admin_usernames() -> Set[str]:
    raw_values = ",".join(
        value
        for value in [
            os.getenv("BOT_ADMIN_USERNAMES", ""),
            os.getenv("DEV_ADMIN_USERNAMES", ""),
        ]
        if value
    )
    usernames: Set[str] = set()
    for chunk in raw_values.split(","):
        normalized = normalize_username(chunk)
        if normalized:
            usernames.add(normalized)
    return usernames


BOT_ADMIN_IDS = parse_admin_ids()
BOT_ADMIN_USERNAMES = parse_admin_usernames()


def is_stats_admin(user: Optional[User]) -> bool:
    if not user:
        return False
    if int(user.id) in BOT_ADMIN_IDS:
        return True
    username = normalize_username(user.username)
    return bool(username and username in BOT_ADMIN_USERNAMES)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    if message.from_user:
        upsert_subscriber(message.from_user)

    if not WEBAPP_URL:
        await message.answer("❌ WEBAPP_URL не задан. Укажи URL мини-приложения в .env")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )
    await message.answer(
        "🕵️ Добро пожаловать в игру «Шпион»!\n\n"
        "Нажми кнопку ниже, чтобы открыть мини-приложение.",
        reply_markup=kb,
    )


@dp.message(Command("stats"))
async def stats(message: Message) -> None:
    if not is_stats_admin(message.from_user):
        await message.answer("⛔ Команда доступна только администратору.")
        return

    init_subscribers_db()
    total = subscribers_count(active_only=False)
    active = subscribers_count(active_only=True)
    mau_30 = subscribers_recent_count(days=30, active_only=False)
    wau_7 = subscribers_recent_count(days=7, active_only=False)
    new_30 = new_subscribers_count(days=30)

    await message.answer(
        "📊 Статистика бота\n\n"
        f"Всего пользователей: {total}\n"
        f"Активных подписчиков: {active}\n"
        f"MAU (30 дней): {mau_30}\n"
        f"WAU (7 дней): {wau_7}\n"
        f"Новых за 30 дней: {new_30}"
    )


async def main() -> None:
    init_subscribers_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
