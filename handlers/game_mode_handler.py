"""
Обработчик выбора режима игры
"""
from telegram import Update
from telegram.ext import ContextTypes
from game.models import GameMode
from keyboards.inline_keyboards import game_mode_keyboard, player_count_keyboard
from storage.game_storage import game_storage


async def game_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик нажатия на кнопку «Начать игру»
    Предлагает выбрать режим игры
    """
    query = update.callback_query
    if not query:
        return

    await query.answer()

    user_id = query.from_user.id
    session = game_storage.get_session(user_id)
    session.is_creator = True
    session.game_id = None
    session.selected_player_count = None

    text = (
        "🎮 **Выбор режима игры**\n\n"
        "Доступные режимы:\n\n"
        "📋 **Стандартный режим**\n"
        "  • 1 игрок — шпион (не знает карту)\n"
        "  • Остальные — обычные игроки (знают карту)\n"
    )

    await query.edit_message_text(
        text,
        reply_markup=game_mode_keyboard(),
        parse_mode="Markdown"
    )


async def mode_standard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик выбора стандартного режима"""
    query = update.callback_query
    if not query:
        return

    await query.answer()

    user_id = query.from_user.id
    session = game_storage.get_session(user_id)
    session.selected_mode = GameMode.STANDARD

    text = (
        "✅ **Стандартный режим выбран**\n\n"
        "Теперь выбери количество игроков (от 3 до 10):"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown"
    )

    # Отправляем клавиатуру с выбором количества игроков
    message = query.message
    chat_id = getattr(message, "chat_id", None)
    if chat_id is None:
        # fallback to user's private chat
        chat_id = query.from_user.id

    await context.bot.send_message(
        chat_id=chat_id,
        text="🎲 **Выбери количество игроков**",
        reply_markup=player_count_keyboard(),
        parse_mode="Markdown"
    )

