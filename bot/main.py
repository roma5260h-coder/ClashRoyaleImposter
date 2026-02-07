import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    if not WEBAPP_URL:
        await message.answer(
            "❌ WEBAPP_URL не задан. Укажи URL мини‑приложения в .env"
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )
    await message.answer(
        "🕵️ Добро пожаловать в игру «Шпион»!\n\n"
        "Нажми кнопку ниже, чтобы открыть мини‑приложение.",
        reply_markup=kb,
    )


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
