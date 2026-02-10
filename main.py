"""
Главный файл Telegram-бота для игры Шпион

Flow бота:
1. /start - приветствие пользователя
2. Нажатие "Начать игру" - выбор режима
3. Выбор режима - выбор количества игроков
4. Выбор количества - создание игры, раздача ролей
5. Личные сообщения каждому игроку
"""

import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)
from config.settings import TELEGRAM_BOT_TOKEN
from handlers.start_handler import start_command
from handlers.game_mode_handler import game_mode_callback, mode_standard_callback
from handlers.game_handler import player_count_callback, close_card_callback, cancel_callback

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Точка входа в приложение"""
    
    # Проверка наличия токена
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Ошибка: TELEGRAM_BOT_TOKEN не установлен в .env файле")
        return
    
    # Создаём приложение
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрируем обработчик команды /start
    app.add_handler(CommandHandler("start", start_command))
    
    # Регистрируем обработчики callback-ов
    # Нажатие "Начать игру" -> выбор режима
    app.add_handler(CallbackQueryHandler(game_mode_callback, pattern="^start_game$"))
    
    # Выбор режима -> выбор количества игроков
    app.add_handler(CallbackQueryHandler(mode_standard_callback, pattern="^mode_standard$"))
    
    # Выбор количества игроков -> создание игры
    app.add_handler(CallbackQueryHandler(player_count_callback, pattern="^players_\\d+$"))

    # Закрытие card modal
    app.add_handler(CallbackQueryHandler(close_card_callback, pattern="^close_card_\\d+_\\d+$"))
    
    # Отмена игры
    app.add_handler(CallbackQueryHandler(cancel_callback, pattern="^cancel$"))
    
    # Запускаем бота
    logger.info("🤖 Бот запущен и готов к работе!")
    logger.info(f"📊 Количество доступных карт: {import_and_load_cards()}")
    
    app.run_polling()


def import_and_load_cards() -> int:
    """Загружаем карты при запуске"""
    from game.card_loader import CardLoader
    try:
        cards = CardLoader.load_cards()
        return len(cards)
    except Exception as e:
        logger.error(f"Ошибка загрузки карт: {e}")
        return 0


if __name__ == "__main__":
    main()
