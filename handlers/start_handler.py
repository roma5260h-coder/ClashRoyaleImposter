"""
Обработчик команды /start
"""
from telegram import Update
from telegram.ext import ContextTypes
from keyboards.inline_keyboards import start_keyboard
from storage.game_storage import game_storage


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start
    Отправляет приветственное сообщение с кнопкой «Начать игру»
    """
    user = update.effective_user
    chat = update.effective_chat
    
    # Получаем сессию пользователя
    session = game_storage.get_session(user.id)
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🕵️ Добро пожаловать в игру **Шпион**!\n\n"
        "Это настольная игра, где один игрок — шпион, а остальные знают одну общую карту.\n"
        "Шпион должен не выдать себя, слушая подсказки других игроков.\n\n"
        "💡 Бот поможет:\n"
        "  • Выбрать режим игры\n"
        "  • Раздать роли игрокам\n"
        "  • Отправить каждому его роль в личное сообщение\n\n"
        "Готов начать?"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=start_keyboard(),
        parse_mode="Markdown"
    )
