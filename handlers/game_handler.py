"""
Обработчик выбора количества игроков и основная логика игры
"""
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from game.models import Role, GameMode
from game.game_manager import game_manager
from keyboards.inline_keyboards import close_card_keyboard
from storage.game_storage import game_storage


async def player_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик выбора количества игроков
    Инициирует создание игры и раздачу ролей
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    # Парсим количество игроков из callback_data
    # Ожидаем формат: "players_N"
    if not query.data:
        return
    
    player_count = int(query.data.split('_')[1])
    
    user_id = query.from_user.id
    session = game_storage.get_session(user_id)
    session.selected_player_count = player_count
    
    message = query.message
    if not message:
        return
    
    chat_id = getattr(message, "chat_id", None)
    if chat_id is None:
        return
    
    # Создаём игру
    game = game_manager.create_game(
        chat_id=chat_id,
        creator_id=user_id,
        mode=session.selected_mode or GameMode.STANDARD,
        player_count=player_count
    )
    
    session.game_id = game.game_id
    
    # Назначаем роли и выбираем карту
    game_manager.assign_roles_and_card(game)

    # В текущем упрощённом демо-режиме привязываем все слоты к создателю.
    # В боевом режиме здесь должны быть реальные Telegram ID участников.
    for player in game.players:
        if player.telegram_id == 0:
            player.telegram_id = user_id
        game_manager.mark_player_joined(game, player.player_id)

    # Стартуем игру только при валидной готовности комнаты.
    # При старте автоматически открывается card modal.
    game_started = game_manager.start_game(game)

    if not game_started:
        waiting_text = (
            f"⏳ **Игра создана, ждём игроков**\n\n"
            f"📊 Игроков в комнате: {len(game.joined_player_ids)}/{len(game.players)}\n"
            f"🗺️ Карта откроется автоматически, когда все игроки войдут."
        )
        await query.edit_message_text(waiting_text, parse_mode="Markdown")
        return
    
    # Отправляем уведомление в основной чат
    confirmation_text = (
        f"✅ **Игра начата**\n\n"
        f"📊 **Параметры игры:**\n"
        f"  • Режим: Стандартный\n"
        f"  • Игроков: {player_count}\n"
        f"  • Статус: {game.status.value}\n\n"
        f"🔐 **Роли распределены** (см. личные сообщения)\n"
        f"🗺️ **Карта открыта как оверлей и закрывается вручную кнопкой.**\n"
    )
    
    await query.edit_message_text(confirmation_text, parse_mode="Markdown")
    
    # Отправляем личные сообщения каждому игроку
    await send_private_messages(game, context)
    
    # Сообщаем в чат, кто начинает
    start_player = game.get_start_player()
    if start_player:
        start_text = (
            f"\n🎮 **Игру начинает: Игрок #{start_player.player_id}**\n\n"
            f"Остальные игроки, слушайте внимательно подсказки!\n"
            f"Ваша задача — вычислить шпиона 🕵️"
        )
        await context.bot.send_message(chat_id=chat_id, text=start_text, parse_mode="Markdown")


async def send_private_messages(game, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправить личные сообщения игрокам с их ролями
    
    Args:
        game: Объект игры
        context: Контекст Telegram
    """
    try:
        for player in game.players:
            if player.role == Role.SPY:
                # Сообщение шпиону
                spy_message = (
                    f"🕵️ **Ты шпион!** (Игрок #{player.player_id})\n\n"
                    f"Тебе не известна карта/локация, которую знают остальные игроки.\n"
                    f"Слушай подсказки и старайся не выдать себя!\n\n"
                    f"Удачи! 🎭\n\n"
                    f"Когда остальные закроют карту, раунд продолжится."
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=player.telegram_id,
                        text=spy_message,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Ошибка отправки сообщения шпиону {player.player_id}: {e}")
            
            else:  # Role.CITIZEN
                # Сообщение обычному игроку
                citizen_message = (
                    f"👤 **Ты обычный игрок!** (Игрок #{player.player_id})\n\n"
                    f"🗺️ **Карта: {game.card.name_ru}**\n\n"
                    f"Эту карту знают только мирные игроки (но не шпион).\n"
                    f"Давай подсказки, не называя карту прямо.\n\n"
                    f"После просмотра закрой карту кнопкой ниже."
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=player.telegram_id,
                        text=citizen_message,
                        parse_mode="Markdown"
                    )
                    
                    # Отправляем изображение карты в виде "модалки" с явным закрытием.
                    if game.card and game.card.image_url:
                        await context.bot.send_photo(
                            chat_id=player.telegram_id,
                            photo=game.card.image_url,
                            caption=f"🗺️ {game.card.name_ru}",
                            reply_markup=close_card_keyboard(game.game_id, player.player_id)
                        )
                except Exception as e:
                    print(f"Ошибка отправки сообщения игроку {player.player_id}: {e}")
    
    except Exception as e:
        print(f"Ошибка при отправке личных сообщений: {e}")


async def close_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик закрытия card modal"""
    query = update.callback_query
    if not query or not query.data:
        return

    # Формат callback_data: close_card_<game_id>_<player_id>
    parts = query.data.split("_")
    if len(parts) != 4:
        await query.answer("Некорректные данные карты", show_alert=True)
        return

    raw_game_id = parts[2]
    raw_player_id = parts[3]

    game = game_manager.get_game(raw_game_id)
    if not game:
        await query.answer("Игра не найдена", show_alert=True)
        return

    await query.answer("✅ Карта закрыта")

    try:
        player_id = int(raw_player_id)
    except ValueError:
        await query.answer("Некорректный игрок", show_alert=True)
        return

    all_cards_closed = game_manager.close_card_for_player(game, player_id)

    message = query.message
    if message:
        try:
            if message.photo:
                await query.edit_message_caption(
                    caption="✅ Карта закрыта. Ожидаем остальных игроков.",
                    reply_markup=None
                )
            else:
                await query.edit_message_text(
                    text="✅ Карта закрыта. Ожидаем остальных игроков.",
                    reply_markup=None
                )
        except BadRequest:
            # Сообщение уже обновлено или недоступно для редактирования.
            pass

    if all_cards_closed:
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=(
                "✅ Все игроки закрыли карту.\n"
                "Игра продолжается, можно начинать обсуждение."
            )
        )


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки отмены"""
    query = update.callback_query
    if not query:
        return
    
    await query.answer("❌ Игра отменена")
    
    user_id = query.from_user.id
    session = game_storage.get_session(user_id)
    
    # Удаляем игру, если она была создана
    if session.game_id:
        game_manager.delete_game(session.game_id)
    
    # Очищаем сессию
    game_storage.delete_session(user_id)
    
    await query.edit_message_text("❌ Игра отменена. Введите /start для новой игры.")
