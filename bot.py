import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher

# Загрузка переменных окружения
load_dotenv()

# Инициализация бота и диспетчера
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
