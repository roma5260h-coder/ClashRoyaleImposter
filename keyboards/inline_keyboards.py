"""
Инлайн-клавиатуры для Telegram-бота
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для /start"""
    buttons = [
        [InlineKeyboardButton("🎮 Начать игру", callback_data="start_game")]
    ]
    return InlineKeyboardMarkup(buttons)


def game_mode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора режима игры"""
    buttons = [
        [InlineKeyboardButton("📋 Стандартный режим", callback_data="mode_standard")]
    ]
    return InlineKeyboardMarkup(buttons)


def player_count_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора количества игроков"""
    buttons = []
    for count in range(3, 11):  # От 3 до 10 игроков
        buttons.append(
            [InlineKeyboardButton(f"{count} игроков", callback_data=f"players_{count}")]
        )
    return InlineKeyboardMarkup(buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    buttons = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel")
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def close_card_keyboard(game_id: int, player_id: int) -> InlineKeyboardMarkup:
    """Кнопка закрытия карточки карты (UI-оверлей)"""
    buttons = [
        [InlineKeyboardButton("✖️ Закрыть карту", callback_data=f"close_card_{game_id}_{player_id}")]
    ]
    return InlineKeyboardMarkup(buttons)
