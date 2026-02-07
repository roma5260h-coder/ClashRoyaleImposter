import asyncio
import logging
from dotenv import load_dotenv

# Загрузка переменных окружения ДО импорта bot
load_dotenv()

from bot import bot, dp
from handlers.game_handlers import router as game_router


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция для запуска бота"""
    
    # Добавляем роутер с обработчиками
    dp.include_router(game_router)
    
    logger.info("🚀 Бот запустился")
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
