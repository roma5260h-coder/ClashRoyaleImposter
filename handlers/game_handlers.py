from typing import cast, Optional
from datetime import datetime, timedelta
import random
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, User
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot import bot
from session import GameSession, GameState
from rooms import RoomSession, RoomState
from game_logic import deal_roles
from data.card_images import get_card_image


# Словарь для хранения игровых сессий по chat_id
game_sessions = {}
room_sessions = {}

MIN_ROOM_PLAYERS = 3
MAX_ROOM_PLAYERS = 12
ROOM_TTL_MINUTES = 60


class GameFSM(StatesGroup):
    """FSM для управления состояниями игры"""
    waiting_format_selection = State()
    waiting_play_mode_selection = State()
    waiting_random_confirm = State()
    waiting_player_count = State()
    waiting_player_action = State()
    waiting_room_action = State()
    waiting_room_code = State()


router = Router()


def _format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Офлайн (один телефон)", callback_data="format_offline")],
            [InlineKeyboardButton(text="Онлайн (комната)", callback_data="format_online")],
        ]
    )


def _play_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Стандартный режим", callback_data="play_standard")],
            [InlineKeyboardButton(text="Рандом режим", callback_data="play_random")],
        ]
    )


def _random_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Продолжить", callback_data="random_continue")]]
    )


def _get_display_name(user: Optional[User]) -> str:
    if not user:
        return "Игрок"
    if user.username:
        return f"@{user.username}"
    return user.full_name


def _generate_room_code() -> str:
    for _ in range(5):
        code = uuid.uuid4().hex[:6].upper()
        if code not in room_sessions:
            return code
    return uuid.uuid4().hex[:8].upper()


def _is_room_expired(room: RoomSession) -> bool:
    if room.state != RoomState.WAITING:
        return False
    return datetime.utcnow() - room.created_at > timedelta(minutes=ROOM_TTL_MINUTES)


def _get_room(code: str) -> Optional[RoomSession]:
    room = room_sessions.get(code)
    if room and _is_room_expired(room):
        del room_sessions[code]
        return None
    return room


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start"""
    chat_id = message.chat.id
    
    # Создаём новую сессию
    game_sessions[chat_id] = GameSession(chat_id=chat_id)
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎮 Начать игру", callback_data="start_game")]]
    )
    
    await message.answer(
        "🕵️ Добро пожаловать в игру «Шпион»!\n\n"
        "Эта игра для одного телефона, передаваемого по кругу.\n"
        "Один игрок будет шпионом, остальные будут знать карту.\n"
        "Ваша задача — вычислить шпиона через подсказки!\n\n"
        "Нажми кнопку ниже, чтобы начать.",
        reply_markup=kb
    )
    await state.clear()


@router.callback_query(F.data == "start_game")
async def start_game(query: CallbackQuery, state: FSMContext):
    """Начало игры — выбор режима"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return
    
    message = cast(Message, query.message)
    chat_id = message.chat.id
    
    if chat_id not in game_sessions:
        await query.answer("Игра не инициализирована. Нажми /start", show_alert=True)
        return
    
    kb = _format_keyboard()
    
    await message.edit_text(
        "📋 Выбери формат игры:\n\n"
        "Офлайн — один телефон, передаётся по кругу.\n"
        "Онлайн — каждый игрок получает роль в личку.",
        reply_markup=kb
    )
    await state.set_state(GameFSM.waiting_format_selection)


@router.callback_query(F.data.in_({"format_offline", "mode_standard"}), GameFSM.waiting_format_selection)
async def select_format_offline(query: CallbackQuery, state: FSMContext):
    """Выбор формата → выбор режима игры"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    message = cast(Message, query.message)
    await state.update_data(format_mode="offline")

    await message.edit_text(
        "🎯 Выбери режим игры:",
        reply_markup=_play_mode_keyboard()
    )
    await state.set_state(GameFSM.waiting_play_mode_selection)


@router.callback_query(F.data.in_({"format_online", "mode_online"}), GameFSM.waiting_format_selection)
async def select_format_online(query: CallbackQuery, state: FSMContext):
    """Выбор формата → выбор режима игры"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    message = cast(Message, query.message)
    await state.update_data(format_mode="online")

    await message.edit_text(
        "🎯 Выбери режим игры:",
        reply_markup=_play_mode_keyboard()
    )
    await state.set_state(GameFSM.waiting_play_mode_selection)


async def _proceed_after_play_mode(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    format_mode = data.get("format_mode")
    play_mode = data.get("play_mode")

    if not format_mode or not play_mode:
        await message.edit_text(
            "Сначала выбери формат игры.",
            reply_markup=_format_keyboard()
        )
        await state.set_state(GameFSM.waiting_format_selection)
        return

    if format_mode == "offline":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=str(i), callback_data=f"players_{i}")]
                for i in range(3, 13)
            ]
        )
        await message.edit_text(
            "👥 Выбери количество игроков (3–12):",
            reply_markup=kb
        )
        await state.set_state(GameFSM.waiting_player_count)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Создать комнату", callback_data="room_create")],
            [InlineKeyboardButton(text="Подключиться к комнате", callback_data="room_join")],
        ]
    )
    await message.edit_text(
        "🌐 Онлайн-режим\n\n"
        "Создай комнату и отправь код друзьям, или подключись к существующей.",
        reply_markup=kb
    )
    await state.set_state(GameFSM.waiting_room_action)


@router.callback_query(F.data == "play_standard", GameFSM.waiting_play_mode_selection)
async def select_play_mode_standard(query: CallbackQuery, state: FSMContext):
    """Стандартный режим"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    message = cast(Message, query.message)
    await state.update_data(play_mode="standard")
    await _proceed_after_play_mode(message, state)


@router.callback_query(F.data == "play_random", GameFSM.waiting_play_mode_selection)
async def select_play_mode_random(query: CallbackQuery, state: FSMContext):
    """Рандом-режим (инфо перед стартом)"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    message = cast(Message, query.message)
    await state.update_data(play_mode="random")

    await message.edit_text(
        "ℹ️ В этом режиме игра может пойти по одному из сценариев:\n"
        "• Стандартный (обычный режим)\n"
        "• Все шпионы\n"
        "• У всех одна карта\n"
        "• У одного игрока другая карта\n"
        "• У всех разные карты\n"
        "• Несколько шпионов\n\n"
        "Нажми «Продолжить», чтобы начать.",
        reply_markup=_random_confirm_keyboard()
    )
    await state.set_state(GameFSM.waiting_random_confirm)


@router.callback_query(F.data == "random_continue", GameFSM.waiting_random_confirm)
async def random_continue(query: CallbackQuery, state: FSMContext):
    """Подтверждение рандом-режима"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    message = cast(Message, query.message)
    data = await state.get_data()
    if data.get("play_mode") != "random":
        await message.edit_text(
            "Сначала выбери режим игры.",
            reply_markup=_play_mode_keyboard()
        )
        await state.set_state(GameFSM.waiting_play_mode_selection)
        return

    await _proceed_after_play_mode(message, state)


@router.callback_query(F.data.startswith("players_"), GameFSM.waiting_player_count)
async def select_player_count(query: CallbackQuery, state: FSMContext):
    """Выбор количества игроков → начало раздачи ролей"""
    if not query.message or not query.data:
        await query.answer("Ошибка: данные не найдены", show_alert=True)
        return
    
    message = cast(Message, query.message)
    chat_id = message.chat.id
    session = game_sessions.get(chat_id)
    
    if not session:
        await query.answer("Ошибка: игра не найдена", show_alert=True)
        return

    data = await state.get_data()
    play_mode = data.get("play_mode")
    format_mode = data.get("format_mode")
    if format_mode != "offline":
        await query.answer("Сначала выбери формат игры", show_alert=True)
        await state.set_state(GameFSM.waiting_format_selection)
        return
    if not play_mode:
        await query.answer("Сначала выбери режим игры", show_alert=True)
        await state.set_state(GameFSM.waiting_format_selection)
        return
    
    try:
        player_count = int(query.data.split("_")[1])
        session.start_new_game("offline", play_mode, player_count)
    except (ValueError, IndexError):
        await query.answer("Ошибка: некорректное количество игроков", show_alert=True)
        return
    
    # Показываем первого игрока
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 Показать карту", callback_data="show_role")]]
    )
    
    await message.edit_text(
        session.get_current_player_message(),
        reply_markup=kb
    )
    await state.set_state(GameFSM.waiting_player_action)


@router.callback_query(F.data == "room_create", GameFSM.waiting_room_action)
async def room_create(query: CallbackQuery, state: FSMContext):
    """Создание комнаты онлайн-режима"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    message = cast(Message, query.message)
    owner_id = query.from_user.id if query.from_user else message.chat.id

    data = await state.get_data()
    play_mode = data.get("play_mode")
    if not play_mode:
        await message.edit_text(
            "Сначала выбери режим игры.",
            reply_markup=_play_mode_keyboard()
        )
        await state.set_state(GameFSM.waiting_play_mode_selection)
        return

    code = _generate_room_code()
    room = RoomSession(room_code=code, owner_id=owner_id, max_players=MAX_ROOM_PLAYERS)
    room.format_mode = "online"
    room.play_mode = play_mode
    room.add_player(owner_id, _get_display_name(query.from_user))
    room_sessions[code] = room

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Начать игру", callback_data=f"room_start:{code}")],
            [InlineKeyboardButton(text="👥 Показать участников", callback_data=f"room_show:{code}")],
        ]
    )

    await message.edit_text(
        "✅ Комната создана!\n\n"
        f"Код комнаты: {code}\n"
        f"Режим: {'Стандартный' if play_mode == 'standard' else 'Рандом'}\n\n"
        "Отправь этот код друзьям. Пусть они нажмут «Подключиться» и введут код.\n\n"
        f"Игроков сейчас: {len(room.players)}/{room.max_players}\n"
        f"Минимум для старта: {MIN_ROOM_PLAYERS}",
        reply_markup=kb
    )
    await state.set_state(GameFSM.waiting_room_action)


@router.callback_query(F.data == "room_join", GameFSM.waiting_room_action)
async def room_join(query: CallbackQuery, state: FSMContext):
    """Запрос кода комнаты"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    message = cast(Message, query.message)
    await message.edit_text("🔑 Введи код комнаты текстом:")
    await state.set_state(GameFSM.waiting_room_code)


@router.message(GameFSM.waiting_room_code)
async def room_join_by_code(message: Message, state: FSMContext):
    """Подключение по коду комнаты"""
    code = (message.text or "").strip().upper().replace(" ", "")
    if not code:
        await message.answer("Отправь код комнаты.")
        return

    room = _get_room(code)
    if not room:
        await message.answer("❌ Комната не найдена или истекла. Попробуй ещё раз.")
        return

    if room.state != RoomState.WAITING:
        await message.answer("❌ Игра уже началась. Подключение закрыто.")
        return

    if room.is_full():
        await message.answer("❌ Комната заполнена.")
        return

    user_id = message.from_user.id if message.from_user else message.chat.id
    added = room.add_player(user_id, _get_display_name(message.from_user))
    if not added:
        await message.answer(f"✅ Ты уже в комнате {room.room_code}.")
        return

    await message.answer(
        "✅ Ты подключился к комнате.\n"
        f"Код комнаты: {room.room_code}\n"
        f"Игроков сейчас: {len(room.players)}/{room.max_players}\n\n"
        "Ожидай начала игры.\n"
        "Если ещё не нажимал /start у бота — нажми, чтобы я смог прислать роль."
    )
    await state.set_state(GameFSM.waiting_room_action)

    try:
        await bot.send_message(
            room.owner_id,
            f"👤 Игрок {_get_display_name(message.from_user)} подключился "
            f"({len(room.players)}/{room.max_players})."
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("room_show:"))
async def room_show(query: CallbackQuery):
    """Показать участников комнаты"""
    if not query.message or not query.data:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    code = query.data.split(":", 1)[1].upper()
    room = _get_room(code)
    if not room:
        await query.answer("Комната не найдена или истекла", show_alert=True)
        return

    players_list = "\n".join(
        [f"{idx}. {name}" for idx, name in enumerate(room.players.values(), start=1)]
    )
    await query.answer()
    await cast(Message, query.message).answer(
        f"👥 Участники комнаты {room.room_code}:\n{players_list}\n\n"
        f"Всего: {len(room.players)}/{room.max_players}"
    )


@router.callback_query(F.data.startswith("room_start:"))
async def room_start(query: CallbackQuery, state: FSMContext):
    """Старт онлайн-игры (только создатель)"""
    if not query.message or not query.data:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return

    message = cast(Message, query.message)
    code = query.data.split(":", 1)[1].upper()
    room = _get_room(code)
    if not room:
        await query.answer("Комната не найдена или истекла", show_alert=True)
        return

    if query.from_user and query.from_user.id != room.owner_id:
        await query.answer("Только создатель может начать игру", show_alert=True)
        return

    if room.state != RoomState.WAITING:
        await query.answer("Игра уже началась", show_alert=True)
        return

    if len(room.players) < MIN_ROOM_PLAYERS:
        await query.answer(
            f"Нужно минимум {MIN_ROOM_PLAYERS} игрока",
            show_alert=True
        )
        return

    if not room.play_mode:
        await query.answer("Сначала выбери режим игры", show_alert=True)
        return

    player_ids = list(room.players.keys())
    spies, cards_for_players, resolved_random_mode = deal_roles(
        player_ids,
        room.play_mode
    )

    room.spy_players = spies
    room.cards_for_players = cards_for_players
    room.resolved_random_mode = resolved_random_mode
    room.state = RoomState.STARTED

    failed: list[str] = []
    for user_id, display in room.players.items():
        try:
            card = cards_for_players.get(user_id)
            if card:
                image_url = get_card_image(card)
                if image_url:
                    try:
                        await bot.send_photo(
                            user_id,
                            image_url,
                            caption=f"🗺️ Карта: {card}"
                        )
                    except Exception:
                        await bot.send_message(user_id, f"🗺️ Карта: {card}")
                else:
                    await bot.send_message(user_id, f"🗺️ Карта: {card}")
            else:
                await bot.send_message(user_id, "🕵️ Ты шпион")
        except Exception:
            failed.append(display)

    starter_id = random.choice(player_ids)
    starter_name = room.players.get(starter_id, "Игрок")
    start_text = f"✅ Роли розданы!\n🎬 Игру начинает: {starter_name}"

    await query.answer()
    try:
        await message.edit_text(start_text)
    except Exception:
        await message.answer(start_text)

    for user_id in room.players.keys():
        if user_id == room.owner_id:
            continue
        try:
            await bot.send_message(user_id, start_text)
        except Exception:
            pass

    # У владельца показываем меню для следующей игры
    try:
        await bot.send_message(
            room.owner_id,
            "Выбери формат для новой игры:",
            reply_markup=_format_keyboard()
        )
        await state.set_state(GameFSM.waiting_format_selection)
    except Exception:
        pass

    if failed:
        try:
            await bot.send_message(
                room.owner_id,
                "⚠️ Не удалось отправить роли этим игрокам:\n"
                + "\n".join(f"- {name}" for name in failed)
                + "\nПопроси их нажать /start и попробовать снова."
            )
        except Exception:
            pass


@router.callback_query(F.data == "show_role", GameFSM.waiting_player_action)
async def show_role(query: CallbackQuery, state: FSMContext):
    """Показываем роль/карту текущему игроку"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return
    
    message = cast(Message, query.message)
    chat_id = message.chat.id
    session = game_sessions.get(chat_id)
    
    if not session or session.state != GameState.ROLE_REVEALING:
        await query.answer("Ошибка: игра не в правильном состоянии", show_alert=True)
        return
    
    role_message = session.get_role_message()
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔐 Закрыть", callback_data="close_role")]]
    )

    card = None
    if session.cards_for_players:
        card = session.cards_for_players.get(session.current_player_number)

    if card:
        image_url = get_card_image(card)
        if image_url:
            await query.answer()
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.answer_photo(
                    image_url,
                    caption=role_message,
                    reply_markup=kb
                )
                return
            except Exception:
                # Если Telegram не смог загрузить картинку, просто покажем текст
                pass

    await message.edit_text(role_message, reply_markup=kb)


@router.callback_query(F.data == "close_role", GameFSM.waiting_player_action)
async def close_role(query: CallbackQuery, state: FSMContext):
    """Закрываем роль и переходим к следующему игроку"""
    if not query.message:
        await query.answer("Ошибка: сообщение не найдено", show_alert=True)
        return
    
    message = cast(Message, query.message)
    chat_id = message.chat.id
    session = game_sessions.get(chat_id)
    
    if not session or session.state != GameState.ROLE_REVEALING:
        await query.answer("Ошибка: игра не в правильном состоянии", show_alert=True)
        return

    is_media_message = bool(message.photo)

    # Переходим к следующему игроку
    is_finished = session.next_player()
    
    if is_finished:
        # Все игроки обработаны — игра начинается
        message_text = (
            session.get_game_started_message()
            + "\n\nВыбери формат для новой игры:"
        )
        kb = _format_keyboard()
        await query.answer()
        if is_media_message:
            try:
                await message.delete()
            except Exception:
                pass
            await message.answer(message_text, reply_markup=kb)
        else:
            await message.edit_text(message_text, reply_markup=kb)
        await state.set_state(GameFSM.waiting_format_selection)
    else:
        # Показываем следующего игрока
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📋 Показать карту", callback_data="show_role")]]
        )

        next_text = (
            "📱 Передайте телефон следующему игроку!\n\n"
            f"{session.get_current_player_message()}"
        )
        await query.answer()
        if is_media_message:
            try:
                await message.delete()
            except Exception:
                pass
            await message.answer(next_text, reply_markup=kb)
        else:
            await message.edit_text(next_text, reply_markup=kb)
