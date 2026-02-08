import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qsl, quote
from urllib.request import Request as UrlRequest, urlopen

from fastapi import FastAPI, HTTPException, Request as FastAPIRequest, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .game_logic import deal_roles
from .data.card_images import get_card_image
from .data.elixir_costs import get_elixir_cost


load_dotenv()

APP_TTL_MINUTES = 60
MIN_PLAYERS = 3
MAX_PLAYERS = 12
IMAGE_CACHE_TTL_SECONDS = 60 * 60 * 24
MIN_TURN_TIME_SECONDS = 5
MAX_TURN_TIME_SECONDS = 30
DEFAULT_TURN_TIME_SECONDS = 8
OFFLINE_STATE_REVEALING = "revealing"
TURN_STATE_WAITING = "waiting"
TURN_STATE_READY_TO_START = "ready_to_start"
TURN_STATE_ACTIVE = "turn_loop_active"
TURN_STATE_FINISHED = "finished"
ROOM_STATE_WAITING = "waiting"
ROOM_STATE_STARTED = "started"
ROOM_STATE_PAUSED = "paused"
HEARTBEAT_STALE_SECONDS = 20
BOT_ID_PREFIX = "bot_"
BOT_NAME_PATTERN = re.compile(r"^Bot (\d+)$")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
INIT_DATA_BYPASS = os.getenv("INIT_DATA_BYPASS", "0") == "1"
DEBUG_RANDOM = os.getenv("DEBUG_RANDOM", "0") == "1"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("spy_game")
APP_ENV = os.getenv("APP_ENV", "").strip().lower()
ROOM_DEBUG = os.getenv("ROOM_DEBUG", "0") == "1" or APP_ENV in {"dev", "development", "local"}
NODE_ENV = os.getenv("NODE_ENV", "").strip().lower()
DEV_TOOLS_ENABLED = (
    os.getenv("DEV_TOOLS_ENABLED", "0") == "1"
    or APP_ENV in {"dev", "development", "local", "test"}
    or bool(NODE_ENV and NODE_ENV != "production")
)


def parse_dev_admin_ids() -> Set[int]:
    raw_values = ",".join(
        value
        for value in [
            os.getenv("DEV_ADMIN_IDS", ""),
            os.getenv("DEV_ADMIN_TG_ID", ""),
        ]
        if value
    )
    admin_ids: Set[int] = set()
    for chunk in raw_values.split(","):
        normalized = chunk.strip()
        if not normalized:
            continue
        try:
            admin_ids.add(int(normalized))
        except ValueError:
            logger.warning("Skipping invalid DEV admin id: %s", normalized)
    return admin_ids


DEV_ADMIN_IDS = parse_dev_admin_ids()


def normalize_tg_username(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().lstrip("@").lower()
    return normalized or None


def parse_dev_admin_usernames() -> Set[str]:
    raw_values = ",".join(
        value
        for value in [
            os.getenv("DEV_ADMIN_USERNAMES", ""),
            os.getenv("DEV_ADMIN_TG_USERNAME", ""),
        ]
        if value
    )
    usernames: Set[str] = set()
    for chunk in raw_values.split(","):
        normalized = normalize_tg_username(chunk)
        if normalized:
            usernames.add(normalized)
    return usernames


DEV_ADMIN_USERNAMES = parse_dev_admin_usernames()
PlayerId = Union[int, str]

app = FastAPI(title="Spy Game API")

allowed_origins = os.getenv("WEBAPP_ORIGINS", "").split(",")
allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
if not allowed_origins:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def handle_unexpected_errors(request: FastAPIRequest, call_next):
    try:
        return await call_next(request)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unhandled server error path=%s method=%s",
            request.url.path,
            request.method,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Произошла ошибка, попробуйте ещё раз"},
        )


class BaseRequest(BaseModel):
    initData: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None


class OfflineStartRequest(BaseRequest):
    game_mode: str
    player_count: int
    random_allowed_modes: Optional[List[str]] = None
    timer_enabled: bool = False
    turn_time_seconds: Optional[int] = None


class OfflineStartResponse(BaseModel):
    session_id: str
    current_player_number: int
    player_count: int
    timer_enabled: bool
    turn_time_seconds: Optional[int] = None


class OfflineTurnRequest(BaseRequest):
    session_id: str


class OfflineTurnStatusResponse(BaseModel):
    timer_enabled: bool
    turn_time_seconds: Optional[int] = None
    turn_active: bool
    turn_state: str
    current_turn_index: int
    current_player_number: int
    turn_started_at: Optional[float] = None
    turns_completed: bool


class OfflineRevealRequest(BaseRequest):
    session_id: str


class OfflineRevealResponse(BaseModel):
    player_number: int
    role: str
    card: Optional[str] = None
    image_url: Optional[str] = None
    elixir_cost: Optional[int] = None


class OfflineCloseRequest(BaseRequest):
    session_id: str


class OfflineCloseResponse(BaseModel):
    finished: bool
    current_player_number: Optional[int] = None
    starter_player_number: Optional[int] = None


class OfflineRestartRequest(BaseRequest):
    session_id: str


class RoomCreateRequest(BaseRequest):
    format_mode: str
    game_mode: str
    random_allowed_modes: Optional[List[str]] = None
    player_limit: int = MAX_PLAYERS
    timer_enabled: bool = False
    turn_time_seconds: Optional[int] = None


class RoomJoinRequest(BaseRequest):
    room_code: str
    format_mode: Optional[str] = None
    game_mode: Optional[str] = None


class RoomActionRequest(BaseRequest):
    room_code: str


class RoomBotsAddRequest(RoomActionRequest):
    count: int = Field(..., ge=1, le=10)


class RoomLeaveResponse(BaseModel):
    left: bool
    room_closed: bool


class RoomPlayer(BaseModel):
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: str
    isBot: bool = False


class RoomInfo(BaseModel):
    room_code: str
    owner_user_id: int
    owner_name: str
    format_mode: str
    play_mode: str
    players: List[RoomPlayer]
    player_count: int
    player_limit: int
    state: str
    can_start: bool
    you_are_owner: bool
    starter_name: Optional[str] = None
    host_name: str
    timer_enabled: bool = False
    turn_time_seconds: Optional[int] = None
    turn_active: bool = False
    turn_state: str = TURN_STATE_WAITING
    current_turn_index: int = 0
    current_turn_name: Optional[str] = None
    turn_started_at: Optional[float] = None
    turns_completed: bool = False
    status_message: Optional[str] = None
    can_manage_bots: bool = False


class RoomStartResponse(BaseModel):
    started: bool
    starter_user_id: str
    starter_name: str


class RoomRestartResponse(RoomStartResponse):
    pass


class RoomRoleResponse(BaseModel):
    role: str
    card: Optional[str] = None
    image_url: Optional[str] = None
    elixir_cost: Optional[int] = None


@dataclass
class OfflineSession:
    session_id: str
    owner_user_id: int
    game_mode: str
    resolved_random_mode: Optional[str]
    player_count: int
    current_player_number: int
    timer_enabled: bool
    turn_time_seconds: Optional[int]
    current_turn_index: int
    players_order: List[int]
    turn_active: bool = False
    turn_started_at: Optional[float] = None
    turns_completed: bool = False
    spy_players: List[int] = field(default_factory=list)
    cards_for_players: Dict[int, Optional[str]] = field(default_factory=dict)
    random_allowed_modes: List[str] = field(default_factory=list)
    starter_player_number: Optional[int] = None
    state: str = OFFLINE_STATE_REVEALING
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RoomSession:
    room_code: str
    owner_user_id: int
    owner_name: str
    format_mode: str
    play_mode: str = "standard"
    players: Dict[PlayerId, Dict[str, object]] = field(default_factory=dict)
    last_seen_by_user: Dict[PlayerId, float] = field(default_factory=dict)
    resolved_random_mode: Optional[str] = None
    random_allowed_modes: List[str] = field(default_factory=list)
    player_limit: int = MAX_PLAYERS
    timer_enabled: bool = False
    turn_time_seconds: Optional[int] = None
    current_turn_index: int = 0
    players_order: List[PlayerId] = field(default_factory=list)
    turn_active: bool = False
    turn_state: str = TURN_STATE_WAITING
    turn_started_at: Optional[float] = None
    turns_completed: bool = False
    spy_user_ids: List[PlayerId] = field(default_factory=list)
    cards_by_user: Dict[PlayerId, Optional[str]] = field(default_factory=dict)
    state: str = ROOM_STATE_WAITING
    starter_user_id: Optional[PlayerId] = None
    last_status_message: Optional[str] = None
    last_status_at: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


offline_sessions: Dict[str, OfflineSession] = {}
rooms: Dict[str, RoomSession] = {}
image_cache: Dict[str, Dict[str, object]] = {}


def cleanup_sessions() -> None:
    now = datetime.utcnow()
    for session_id, session in list(offline_sessions.items()):
        if now - session.created_at > timedelta(minutes=APP_TTL_MINUTES):
            del offline_sessions[session_id]
    for room_code, room in list(rooms.items()):
        if now - room.created_at > timedelta(minutes=APP_TTL_MINUTES) and room.state == ROOM_STATE_WAITING:
            del rooms[room_code]


def parse_init_data(init_data: str) -> Dict[str, str]:
    return dict(parse_qsl(init_data, keep_blank_values=True))


def verify_init_data(init_data: str) -> Dict[str, str]:
    if INIT_DATA_BYPASS:
        data = parse_init_data(init_data)
        if "user" not in data:
            raise HTTPException(status_code=401, detail="user not provided in initData")
        try:
            return json.loads(data["user"])
        except json.JSONDecodeError:
            raise HTTPException(status_code=401, detail="user data invalid")

    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not configured")

    data = parse_init_data(init_data)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="initData hash missing")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(data.items())
    )
    # Telegram WebApp signature verification (https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app)
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="initData signature invalid")

    user_json = data.get("user")
    if not user_json:
        raise HTTPException(status_code=401, detail="user not provided in initData")

    try:
        return json.loads(user_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=401, detail="user data invalid")


def _extract_name(user: Dict[str, str]) -> str:
    full_name = " ".join(
        part for part in [user.get("first_name"), user.get("last_name")] if part
    )
    return full_name.strip()


def require_display_name(user: Dict[str, str]) -> str:
    name = _extract_name(user)
    if not name:
        raise HTTPException(status_code=400, detail="Не удалось получить имя из Telegram")
    return name


def build_player_entry(user: Dict[str, str], index: int) -> Dict[str, object]:
    name = require_display_name(user)
    return {
        "user_id": int(user.get("id", 0)),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "display_name": name,
        "is_bot": False,
    }


def build_bot_entry(bot_id: str, bot_number: int) -> Dict[str, object]:
    return {
        "user_id": bot_id,
        "first_name": None,
        "last_name": None,
        "display_name": f"Bot {bot_number}",
        "is_bot": True,
    }


def build_image_proxy_url(card_name: str) -> Optional[str]:
    if not get_card_image(card_name):
        return None
    return f"/api/cards/image?name={quote(card_name)}"


def fetch_remote_image(url: str) -> Dict[str, object]:
    request = UrlRequest(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://clash-royale.fandom.com/",
        },
    )
    with urlopen(request, timeout=10) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type") or "image/jpeg"
    return {"content": content, "content_type": content_type}


def normalizeRoomCode(code: str) -> str:
    normalized = unicodedata.normalize("NFKC", code or "")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = "".join(ch for ch in normalized if ch.isalnum())
    return normalized.upper()


def room_storage_keys_preview(limit: int = 30) -> List[str]:
    keys = sorted(rooms.keys())
    if len(keys) <= limit:
        return keys
    return keys[:limit] + ["..."]


def debug_room_storage(event: str, raw_code: Optional[str], normalized_code: Optional[str]) -> None:
    if not ROOM_DEBUG:
        return
    logger.info(
        "[room_debug] %s raw=%r normalized=%r total_rooms=%s keys=%s",
        event,
        raw_code,
        normalized_code,
        len(rooms),
        room_storage_keys_preview(),
    )


def generate_room_code() -> str:
    for _ in range(5):
        code = normalizeRoomCode(uuid.uuid4().hex[:6])
        if code not in rooms:
            return code
    return normalizeRoomCode(uuid.uuid4().hex[:8])


def normalize_timer_settings(timer_enabled: bool, turn_time_seconds: Optional[int]) -> Tuple[bool, Optional[int]]:
    if not timer_enabled:
        return False, None
    if turn_time_seconds is None:
        turn_time_seconds = DEFAULT_TURN_TIME_SECONDS
    if turn_time_seconds < MIN_TURN_TIME_SECONDS or turn_time_seconds > MAX_TURN_TIME_SECONDS:
        raise HTTPException(status_code=400, detail="Неверное значение времени хода")
    return True, turn_time_seconds


def clamp_turn_index(current_turn_index: int, total_players: int, context: str) -> int:
    if total_players <= 0:
        return 0
    clamped = max(0, min(current_turn_index, total_players - 1))
    if clamped != current_turn_index:
        logger.warning(
            "%s: current_turn_index=%s out of range for total_players=%s, clamped to %s",
            context,
            current_turn_index,
            total_players,
            clamped,
        )
    return clamped


def ensure_offline_players_order(session: OfflineSession) -> None:
    if session.players_order:
        return
    if session.player_count <= 0:
        logger.error(
            "Offline session %s has invalid player_count=%s; fallback to [1]",
            session.session_id,
            session.player_count,
        )
        session.players_order = [1]
    else:
        session.players_order = list(range(1, session.player_count + 1))
    session.current_turn_index = 0
    logger.warning(
        "Offline session %s had empty players_order; rebuilt=%s",
        session.session_id,
        session.players_order,
    )


def ensure_room_players_order(room: RoomSession) -> None:
    if room.players_order:
        return
    if room.players:
        room.players_order = list(room.players.keys())
        room.current_turn_index = 0
        logger.warning(
            "Room %s had empty players_order; rebuilt from players list",
            room.room_code,
        )
        return
    room.players_order = []
    room.current_turn_index = 0
    logger.warning("Room %s has no players while resolving turn order", room.room_code)


def set_room_status_message(room: RoomSession, message: str) -> None:
    room.last_status_message = message
    room.last_status_at = time.time()


def real_room_player_ids(room: RoomSession) -> List[int]:
    return [player_id for player_id in room.players.keys() if isinstance(player_id, int)]


def touch_room_user(room: RoomSession, user_id: PlayerId) -> None:
    if user_id in room.players:
        room.last_seen_by_user[user_id] = time.time()


def pause_room_after_participant_change(room: RoomSession, message: str) -> None:
    if room.state in (ROOM_STATE_STARTED, ROOM_STATE_PAUSED):
        room.state = ROOM_STATE_PAUSED
        room.turn_active = False
        room.turn_started_at = None
    set_room_status_message(room, message)


def remove_room_participant(room: RoomSession, user_id: PlayerId, reason_message: str) -> bool:
    entry = room.players.get(user_id)
    if not entry:
        return False
    display_name = str(entry.get("display_name") or f"Игрок {user_id}")

    removed_index: Optional[int] = None
    if user_id in room.players_order:
        removed_index = room.players_order.index(user_id)
        room.players_order.pop(removed_index)

    del room.players[user_id]
    room.last_seen_by_user.pop(user_id, None)
    room.cards_by_user.pop(user_id, None)
    room.spy_user_ids = [spy_id for spy_id in room.spy_user_ids if spy_id != user_id]

    if room.starter_user_id == user_id:
        room.starter_user_id = room.players_order[0] if room.players_order else None

    if room.players_order:
        if removed_index is not None:
            if removed_index < room.current_turn_index:
                room.current_turn_index -= 1
            elif removed_index == room.current_turn_index and room.current_turn_index >= len(room.players_order):
                room.current_turn_index = 0
        room.current_turn_index = clamp_turn_index(
            room.current_turn_index,
            len(room.players_order),
            f"room:{room.room_code}",
        )
    else:
        room.current_turn_index = 0
        room.turn_active = False
        room.turn_started_at = None
        room.turn_state = TURN_STATE_FINISHED
        room.turns_completed = True

    if room.owner_user_id == user_id and room.players:
        real_ids_in_order = [player_id for player_id in room.players_order if isinstance(player_id, int)]
        fallback_real_ids = real_room_player_ids(room)
        next_owner_id: Optional[int] = (
            real_ids_in_order[0]
            if real_ids_in_order
            else (fallback_real_ids[0] if fallback_real_ids else None)
        )
        if next_owner_id is not None:
            room.owner_user_id = next_owner_id
            new_owner_entry = room.players.get(next_owner_id)
            room.owner_name = str((new_owner_entry or {}).get("display_name") or "")
        else:
            room.owner_name = ""

    pause_room_after_participant_change(room, f"{display_name} {reason_message}")
    return True


def drop_stale_room_players(room: RoomSession) -> bool:
    if room.state == ROOM_STATE_WAITING:
        # Do not auto-expire waiting lobby participants; otherwise freshly created rooms
        # may disappear before the second player joins.
        return False
    now = time.time()
    stale_user_ids = [
        user_id
        for user_id, last_seen in room.last_seen_by_user.items()
        if user_id in room.players and now - last_seen > HEARTBEAT_STALE_SECONDS
    ]
    for user_id in stale_user_ids:
        remove_room_participant(room, user_id, "вышел из комнаты")
    return len(room.players) == 0 or len(real_room_player_ids(room)) == 0


def is_dev_admin(user_id: int, username: Optional[str]) -> bool:
    if user_id in DEV_ADMIN_IDS:
        return True
    normalized_username = normalize_tg_username(username)
    if normalized_username and normalized_username in DEV_ADMIN_USERNAMES:
        return True
    return False


def ensure_room_dev_bot_access(room: RoomSession, user_id: int, username: Optional[str]) -> None:
    if not DEV_TOOLS_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    if user_id not in room.players:
        raise HTTPException(status_code=403, detail="Вы не в комнате")
    if room.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Только хост может управлять ботами")
    if not is_dev_admin(user_id, username):
        raise HTTPException(status_code=403, detail="DEV доступ запрещён")


def next_bot_number(room: RoomSession) -> int:
    max_number = 0
    for entry in room.players.values():
        if not bool(entry.get("is_bot")):
            continue
        name = str(entry.get("display_name") or "")
        match = BOT_NAME_PATTERN.match(name)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return max_number + 1


def generate_bot_id(room: RoomSession) -> str:
    for _ in range(5):
        candidate = f"{BOT_ID_PREFIX}{uuid.uuid4().hex[:8]}"
        if candidate not in room.players:
            return candidate
    return f"{BOT_ID_PREFIX}{uuid.uuid4().hex}"


def add_room_bots(room: RoomSession, requested_count: int) -> int:
    available_slots = max(0, room.player_limit - len(room.players))
    to_add = min(max(requested_count, 0), available_slots)
    if to_add <= 0:
        return 0

    start_number = next_bot_number(room)
    for offset in range(to_add):
        bot_id = generate_bot_id(room)
        bot_number = start_number + offset
        room.players[bot_id] = build_bot_entry(bot_id, bot_number)
    return to_add


def clear_room_bots(room: RoomSession) -> int:
    bot_ids = [player_id for player_id, entry in room.players.items() if bool(entry.get("is_bot"))]
    removed = 0
    for bot_id in bot_ids:
        if remove_room_participant(room, bot_id, "удалён из комнаты"):
            removed += 1
    return removed


def normalize_offline_turn_state(session: OfflineSession) -> bool:
    if not session.timer_enabled:
        session.turn_time_seconds = None
        session.turn_started_at = None
        session.turn_active = False
        session.turns_completed = session.state == TURN_STATE_FINISHED
        return False

    if session.turn_time_seconds is None:
        logger.warning(
            "Offline session %s has timer_enabled=true but turn_time_seconds=None; using default=%s",
            session.session_id,
            DEFAULT_TURN_TIME_SECONDS,
        )
        session.turn_time_seconds = DEFAULT_TURN_TIME_SECONDS
    elif session.turn_time_seconds < MIN_TURN_TIME_SECONDS or session.turn_time_seconds > MAX_TURN_TIME_SECONDS:
        logger.warning(
            "Offline session %s has invalid turn_time_seconds=%s; using default=%s",
            session.session_id,
            session.turn_time_seconds,
            DEFAULT_TURN_TIME_SECONDS,
        )
        session.turn_time_seconds = DEFAULT_TURN_TIME_SECONDS

    ensure_offline_players_order(session)
    session.current_turn_index = clamp_turn_index(
        session.current_turn_index,
        len(session.players_order),
        f"offline:{session.session_id}",
    )

    if not session.players_order:
        session.turns_completed = True
        session.turn_active = False
        session.state = TURN_STATE_FINISHED
        session.turn_started_at = None
        return False
    return True


def normalize_room_turn_state(room: RoomSession) -> bool:
    if not room.timer_enabled:
        room.turn_time_seconds = None
        room.turn_started_at = None
        room.turn_active = False
        room.turns_completed = room.turn_state == TURN_STATE_FINISHED
        return False

    if room.turn_time_seconds is None:
        logger.warning(
            "Room %s has timer_enabled=true but turn_time_seconds=None; using default=%s",
            room.room_code,
            DEFAULT_TURN_TIME_SECONDS,
        )
        room.turn_time_seconds = DEFAULT_TURN_TIME_SECONDS
    elif room.turn_time_seconds < MIN_TURN_TIME_SECONDS or room.turn_time_seconds > MAX_TURN_TIME_SECONDS:
        logger.warning(
            "Room %s has invalid turn_time_seconds=%s; using default=%s",
            room.room_code,
            room.turn_time_seconds,
            DEFAULT_TURN_TIME_SECONDS,
        )
        room.turn_time_seconds = DEFAULT_TURN_TIME_SECONDS

    ensure_room_players_order(room)
    room.current_turn_index = clamp_turn_index(
        room.current_turn_index,
        len(room.players_order),
        f"room:{room.room_code}",
    )

    if not room.players_order:
        room.turns_completed = True
        room.turn_active = False
        room.turn_state = TURN_STATE_FINISHED
        room.turn_started_at = None
        return False
    return True


def current_offline_turn_player(session: OfflineSession) -> int:
    ensure_offline_players_order(session)
    session.current_turn_index = clamp_turn_index(
        session.current_turn_index,
        len(session.players_order),
        f"offline:{session.session_id}",
    )
    if not session.players_order:
        return max(1, session.current_player_number)
    return session.players_order[session.current_turn_index]


def current_room_turn_user_id(room: RoomSession) -> Optional[PlayerId]:
    ensure_room_players_order(room)
    room.current_turn_index = clamp_turn_index(
        room.current_turn_index,
        len(room.players_order),
        f"room:{room.room_code}",
    )
    if not room.players_order:
        return None
    return room.players_order[room.current_turn_index]


def advance_offline_turn(session: OfflineSession) -> None:
    if session.state != TURN_STATE_ACTIVE or not session.turn_active:
        return
    if not normalize_offline_turn_state(session):
        return
    if session.turn_started_at is None:
        return

    assert session.turn_time_seconds is not None
    now = time.time()
    elapsed = now - session.turn_started_at
    if elapsed < session.turn_time_seconds:
        return

    steps_elapsed = int(elapsed // session.turn_time_seconds)
    if steps_elapsed <= 0:
        return

    session.current_turn_index = (session.current_turn_index + steps_elapsed) % len(session.players_order)
    session.turn_started_at += steps_elapsed * session.turn_time_seconds
    logger.info(
        "Offline session %s advanced to turn index=%s",
        session.session_id,
        session.current_turn_index,
    )


def advance_room_turn(room: RoomSession) -> None:
    if room.state != ROOM_STATE_STARTED or room.turn_state != TURN_STATE_ACTIVE or not room.turn_active:
        return
    if not normalize_room_turn_state(room):
        return
    if room.turn_started_at is None:
        return

    assert room.turn_time_seconds is not None
    now = time.time()
    elapsed = now - room.turn_started_at
    if elapsed < room.turn_time_seconds:
        return

    steps_elapsed = int(elapsed // room.turn_time_seconds)
    if steps_elapsed <= 0:
        return

    room.current_turn_index = (room.current_turn_index + steps_elapsed) % len(room.players_order)
    room.turn_started_at += steps_elapsed * room.turn_time_seconds
    logger.info(
        "Room %s advanced to turn index=%s",
        room.room_code,
        room.current_turn_index,
    )


def build_offline_turn_status_response(session: OfflineSession) -> OfflineTurnStatusResponse:
    current_number = current_offline_turn_player(session)
    session.turns_completed = session.state == TURN_STATE_FINISHED
    return OfflineTurnStatusResponse(
        timer_enabled=session.timer_enabled,
        turn_time_seconds=session.turn_time_seconds,
        turn_active=session.turn_active,
        turn_state=session.state,
        current_turn_index=session.current_turn_index,
        current_player_number=current_number,
        turn_started_at=session.turn_started_at,
        turns_completed=session.turns_completed,
    )


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth", response_model=AuthResponse)
async def auth(request: BaseRequest) -> AuthResponse:
    user = verify_init_data(request.initData)
    return AuthResponse(
        user_id=int(user.get("id", 0)),
        username=user.get("username"),
        full_name=require_display_name(user),
    )


@app.post("/api/offline/start", response_model=OfflineStartResponse)
async def offline_start(request: OfflineStartRequest) -> OfflineStartResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    if request.player_count < MIN_PLAYERS or request.player_count > MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Invalid player count")
    if request.game_mode not in ("standard", "random"):
        raise HTTPException(status_code=400, detail="Invalid game mode")

    session_id = uuid.uuid4().hex
    random_allowed = request.random_allowed_modes
    if request.game_mode == "random" and random_allowed is not None:
        unique_allowed = list(dict.fromkeys(random_allowed))
        if len(unique_allowed) < 2:
            raise HTTPException(status_code=400, detail="Выберите минимум два режима")
        random_allowed = unique_allowed

    timer_enabled, turn_time_seconds = normalize_timer_settings(
        request.timer_enabled, request.turn_time_seconds
    )

    players = list(range(1, request.player_count + 1))
    try:
        spies, cards_for_players, resolved_mode = deal_roles(
            players,
            request.game_mode,
            random_allowed,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Недостаточно режимов для случайного выбора")
    log_random("offline_start", players, spies)

    offline_sessions[session_id] = OfflineSession(
        session_id=session_id,
        owner_user_id=user_id,
        game_mode=request.game_mode,
        resolved_random_mode=resolved_mode,
        player_count=request.player_count,
        current_player_number=1,
        timer_enabled=timer_enabled,
        turn_time_seconds=turn_time_seconds,
        current_turn_index=0,
        players_order=players,
        turn_active=False,
        turn_started_at=None,
        turns_completed=False,
        spy_players=spies,
        cards_for_players=cards_for_players,
        random_allowed_modes=random_allowed or [],
        starter_player_number=None,
    )

    return OfflineStartResponse(
        session_id=session_id,
        current_player_number=1,
        player_count=request.player_count,
        timer_enabled=timer_enabled,
        turn_time_seconds=turn_time_seconds,
    )


@app.post("/api/offline/reveal", response_model=OfflineRevealResponse)
async def offline_reveal(request: OfflineRevealRequest) -> OfflineRevealResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    session = offline_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    player_number = session.current_player_number
    card = session.cards_for_players.get(player_number)
    if card:
        image_url = build_image_proxy_url(card)
        return OfflineRevealResponse(
            player_number=player_number,
            role="card",
            card=card,
            image_url=image_url,
            elixir_cost=get_elixir_cost(card),
        )
    return OfflineRevealResponse(
        player_number=player_number,
        role="spy",
        card=None,
    )


@app.post("/api/offline/close", response_model=OfflineCloseResponse)
async def offline_close(request: OfflineCloseRequest) -> OfflineCloseResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    session = offline_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if session.current_player_number < session.player_count:
        session.current_player_number += 1
        return OfflineCloseResponse(
            finished=False,
            current_player_number=session.current_player_number,
        )

    starter = random_int(1, session.player_count)
    session.starter_player_number = starter

    if session.timer_enabled:
        session.state = TURN_STATE_READY_TO_START
        session.current_turn_index = session.players_order.index(starter)
        session.turn_started_at = None
        session.turn_active = False
        session.turns_completed = False
    else:
        session.state = TURN_STATE_FINISHED
        session.current_turn_index = 0
        session.turn_started_at = None
        session.turn_active = False
        session.turns_completed = True
    return OfflineCloseResponse(
        finished=True,
        starter_player_number=starter,
    )


@app.post("/api/offline/restart", response_model=OfflineStartResponse)
async def offline_restart(request: OfflineRestartRequest) -> OfflineStartResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    session = offline_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    random_allowed = session.random_allowed_modes or None
    players = list(range(1, session.player_count + 1))
    try:
        spies, cards_for_players, resolved_mode = deal_roles(
            players,
            session.game_mode,
            random_allowed,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Недостаточно режимов для случайного выбора")
    log_random("offline_restart", players, spies)

    session.spy_players = spies
    session.cards_for_players = cards_for_players
    session.resolved_random_mode = resolved_mode
    session.current_player_number = 1
    session.state = OFFLINE_STATE_REVEALING
    session.current_turn_index = 0
    session.turn_started_at = None
    session.turn_active = False
    session.turns_completed = False
    session.starter_player_number = None

    return OfflineStartResponse(
        session_id=session.session_id,
        current_player_number=1,
        player_count=session.player_count,
        timer_enabled=session.timer_enabled,
        turn_time_seconds=session.turn_time_seconds,
    )


@app.post("/api/offline/turn/status", response_model=OfflineTurnStatusResponse)
async def offline_turn_status(request: OfflineTurnRequest) -> OfflineTurnStatusResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    session = offline_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    advance_offline_turn(session)
    return build_offline_turn_status_response(session)


@app.post("/api/offline/turn/start", response_model=OfflineTurnStatusResponse)
async def offline_turn_start(request: OfflineTurnRequest) -> OfflineTurnStatusResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    session = offline_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not session.timer_enabled:
        raise HTTPException(status_code=400, detail="Timer disabled")
    if not normalize_offline_turn_state(session):
        raise HTTPException(status_code=400, detail="Timer disabled")
    if session.state == TURN_STATE_FINISHED:
        raise HTTPException(status_code=400, detail="Игра уже завершена")
    if session.state not in (TURN_STATE_READY_TO_START, TURN_STATE_ACTIVE):
        raise HTTPException(status_code=400, detail="Сначала завершите раздачу ролей")

    session.state = TURN_STATE_ACTIVE
    session.turn_active = True
    if session.turn_started_at is None:
        session.turn_started_at = time.time()
    advance_offline_turn(session)
    return build_offline_turn_status_response(session)


@app.post("/api/offline/turn/finish", response_model=OfflineTurnStatusResponse)
async def offline_turn_finish(request: OfflineTurnRequest) -> OfflineTurnStatusResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    session = offline_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not session.timer_enabled:
        raise HTTPException(status_code=400, detail="Timer disabled")
    if session.state == OFFLINE_STATE_REVEALING:
        raise HTTPException(status_code=400, detail="Сначала завершите раздачу ролей")

    session.state = TURN_STATE_FINISHED
    session.turn_active = False
    session.turn_started_at = None
    session.turns_completed = True
    return build_offline_turn_status_response(session)


def random_int(start: int, end: int) -> int:
    return secrets.randbelow(end - start + 1) + start


@app.post("/api/room/create", response_model=RoomInfo)
async def room_create(request: RoomCreateRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    if request.format_mode != "online":
        raise HTTPException(status_code=400, detail="Invalid format mode")
    if request.game_mode not in ("standard", "random"):
        raise HTTPException(status_code=400, detail="Invalid game mode")
    if request.player_limit < MIN_PLAYERS or request.player_limit > MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Неверный лимит игроков")

    random_allowed = request.random_allowed_modes
    if request.game_mode == "random" and random_allowed is not None:
        unique_allowed = list(dict.fromkeys(random_allowed))
        if len(unique_allowed) < 2:
            raise HTTPException(status_code=400, detail="Выберите минимум два режима")
        random_allowed = unique_allowed

    timer_enabled, turn_time_seconds = normalize_timer_settings(
        request.timer_enabled, request.turn_time_seconds
    )

    room_code = normalizeRoomCode(generate_room_code())
    owner_entry = build_player_entry(user, 1)
    room = RoomSession(
        room_code=room_code,
        owner_user_id=user_id,
        owner_name=str(owner_entry["display_name"]),
        format_mode=request.format_mode,
        play_mode=request.game_mode,
        random_allowed_modes=random_allowed or [],
        player_limit=request.player_limit,
        timer_enabled=timer_enabled,
        turn_time_seconds=turn_time_seconds,
        current_turn_index=0,
        players_order=[],
        turn_active=False,
        turn_state=TURN_STATE_WAITING,
        turn_started_at=None,
        turns_completed=False,
    )
    room.players[user_id] = owner_entry
    touch_room_user(room, user_id)
    rooms[room_code] = room
    debug_room_storage("create", room_code, room_code)

    return room_to_info(room, user_id, username)


@app.post("/api/room/join", response_model=RoomInfo)
async def room_join(request: RoomJoinRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    raw_room_code = request.room_code
    room_code = normalizeRoomCode(raw_room_code)
    debug_room_storage("join:before_lookup", raw_room_code, room_code)

    room = rooms.get(room_code)
    if not room:
        debug_room_storage("join:not_found", raw_room_code, room_code)
        raise HTTPException(status_code=404, detail="Комната не найдена")
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        debug_room_storage("join:removed_stale_room", raw_room_code, room_code)
        raise HTTPException(status_code=404, detail="Комната не найдена")
    if room.format_mode != "online":
        raise HTTPException(status_code=400, detail="Эта комната доступна только в онлайн-режиме")
    if request.format_mode and request.format_mode != "online":
        raise HTTPException(status_code=400, detail="Эта комната доступна только в онлайн-режиме")
    if request.game_mode and request.game_mode != room.play_mode:
        logger.info(
            "room_join ignored mismatched game_mode request=%s room=%s code=%s user=%s",
            request.game_mode,
            room.play_mode,
            room.room_code,
            user_id,
        )
    if room.state != ROOM_STATE_WAITING:
        raise HTTPException(status_code=400, detail="Игра уже началась")
    if user_id not in room.players and len(room.players) >= room.player_limit:
        raise HTTPException(status_code=400, detail="Комната заполнена")

    if user_id not in room.players:
        entry = build_player_entry(user, len(room.players) + 1)
        room.players[user_id] = entry
    touch_room_user(room, user_id)
    debug_room_storage("join:success", raw_room_code, room_code)

    return room_to_info(room, user_id, username)


@app.post("/api/room/bots/add", response_model=RoomInfo)
async def room_bots_add(request: RoomBotsAddRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    ensure_room_dev_bot_access(room, user_id, username)
    if room.state != ROOM_STATE_WAITING:
        raise HTTPException(status_code=400, detail="Добавлять ботов можно только до старта игры")

    touch_room_user(room, user_id)
    added = add_room_bots(room, request.count)
    if added <= 0:
        raise HTTPException(status_code=400, detail="Комната заполнена")
    set_room_status_message(room, f"Добавлено ботов: {added}")
    if ROOM_DEBUG:
        logger.info(
            "[room_debug] bots:add room=%s requested=%s added=%s players=%s/%s",
            room.room_code,
            request.count,
            added,
            len(room.players),
            room.player_limit,
        )
    return room_to_info(room, user_id, username)


@app.post("/api/room/bots/fill", response_model=RoomInfo)
async def room_bots_fill(request: RoomActionRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    ensure_room_dev_bot_access(room, user_id, username)
    if room.state != ROOM_STATE_WAITING:
        raise HTTPException(status_code=400, detail="Добавлять ботов можно только до старта игры")

    touch_room_user(room, user_id)
    remaining = max(0, room.player_limit - len(room.players))
    if remaining <= 0:
        raise HTTPException(status_code=400, detail="Комната заполнена")
    added = add_room_bots(room, remaining)
    set_room_status_message(room, f"Добавлено ботов: {added}")
    if ROOM_DEBUG:
        logger.info(
            "[room_debug] bots:fill room=%s added=%s players=%s/%s",
            room.room_code,
            added,
            len(room.players),
            room.player_limit,
        )
    return room_to_info(room, user_id, username)


@app.post("/api/room/bots/clear", response_model=RoomInfo)
async def room_bots_clear(request: RoomActionRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    ensure_room_dev_bot_access(room, user_id, username)
    if room.state != ROOM_STATE_WAITING:
        raise HTTPException(status_code=400, detail="Удалять ботов можно только до старта игры")

    touch_room_user(room, user_id)
    removed = clear_room_bots(room)
    if removed > 0:
        set_room_status_message(room, f"Удалено ботов: {removed}")
    else:
        set_room_status_message(room, "Ботов в комнате нет")
    if ROOM_DEBUG:
        logger.info(
            "[room_debug] bots:clear room=%s removed=%s players=%s/%s",
            room.room_code,
            removed,
            len(room.players),
            room.player_limit,
        )
    return room_to_info(room, user_id, username)


@app.post("/api/room/status", response_model=RoomInfo)
async def room_status(request: RoomActionRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if user_id not in room.players:
        raise HTTPException(status_code=403, detail="Вы вышли из комнаты")
    touch_room_user(room, user_id)
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        raise HTTPException(status_code=404, detail="Room not found")

    return room_to_info(room, user_id, username)


@app.post("/api/room/start", response_model=RoomStartResponse)
async def room_start(request: RoomActionRequest) -> RoomStartResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    touch_room_user(room, user_id)
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only owner can start")
    if room.state != ROOM_STATE_WAITING:
        raise HTTPException(status_code=400, detail="Game already started")
    if len(room.players) < MIN_PLAYERS:
        raise HTTPException(status_code=400, detail="Not enough players")

    players = list(room.players.keys())
    try:
        spies, cards_by_user, resolved_mode = deal_roles(
            players,
            room.play_mode,
            room.random_allowed_modes,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Недостаточно режимов для случайного выбора")
    log_random("room_start", players, spies)
    room.spy_user_ids = spies
    room.cards_by_user = cards_by_user
    room.resolved_random_mode = resolved_mode
    room.state = ROOM_STATE_STARTED
    room.players_order = players
    starter_user_id = random_choice(players)
    room.starter_user_id = starter_user_id
    room.current_turn_index = room.players_order.index(starter_user_id)
    room.turn_started_at = None
    room.turn_active = False
    if room.timer_enabled:
        room.turn_state = TURN_STATE_READY_TO_START
        room.turns_completed = False
    else:
        room.turn_state = TURN_STATE_FINISHED
        room.turns_completed = True

    starter_entry = room.players.get(starter_user_id)
    starter_name = str(starter_entry.get("display_name") or "") if starter_entry else ""
    room.last_status_message = None
    room.last_status_at = None
    return RoomStartResponse(
        started=True,
        starter_user_id=str(starter_user_id),
        starter_name=starter_name,
    )


@app.post("/api/room/role", response_model=RoomRoleResponse)
async def room_role(request: RoomActionRequest) -> RoomRoleResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.state not in (ROOM_STATE_STARTED, ROOM_STATE_PAUSED):
        raise HTTPException(status_code=400, detail="Game not started")
    if user_id not in room.players:
        raise HTTPException(status_code=403, detail="Not in room")
    touch_room_user(room, user_id)
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        raise HTTPException(status_code=404, detail="Room not found")

    card = room.cards_by_user.get(user_id)
    if card:
        image_url = build_image_proxy_url(card)
        return RoomRoleResponse(role="card", card=card, image_url=image_url, elixir_cost=get_elixir_cost(card))
    return RoomRoleResponse(role="spy", card=None)


@app.post("/api/room/restart", response_model=RoomRestartResponse)
async def room_restart(request: RoomActionRequest) -> RoomRestartResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    touch_room_user(room, user_id)
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only owner can restart")
    if len(room.players) < MIN_PLAYERS:
        raise HTTPException(status_code=400, detail="Недостаточно игроков для перезапуска")

    players = list(room.players.keys())
    try:
        spies, cards_by_user, resolved_mode = deal_roles(
            players,
            room.play_mode,
            room.random_allowed_modes,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Недостаточно режимов для случайного выбора")
    log_random("room_restart", players, spies)

    room.spy_user_ids = spies
    room.cards_by_user = cards_by_user
    room.resolved_random_mode = resolved_mode
    room.state = ROOM_STATE_STARTED
    room.players_order = players
    room.starter_user_id = random_choice(players)
    room.current_turn_index = room.players_order.index(room.starter_user_id)
    room.turn_started_at = None
    room.turn_active = False
    if room.timer_enabled:
        room.turn_state = TURN_STATE_READY_TO_START
        room.turns_completed = False
    else:
        room.turn_state = TURN_STATE_FINISHED
        room.turns_completed = True
    starter_entry = room.players.get(room.starter_user_id)
    starter_name = str(starter_entry.get("display_name") or "") if starter_entry else ""
    room.last_status_message = None
    room.last_status_at = None

    return RoomRestartResponse(
        started=True,
        starter_user_id=str(room.starter_user_id or ""),
        starter_name=starter_name,
    )


@app.post("/api/room/turn/start", response_model=RoomInfo)
async def room_turn_start(request: RoomActionRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    touch_room_user(room, user_id)
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        raise HTTPException(status_code=404, detail="Room not found")
    if room.state == ROOM_STATE_PAUSED:
        raise HTTPException(status_code=400, detail="Игра на паузе")
    if room.state != ROOM_STATE_STARTED:
        raise HTTPException(status_code=400, detail="Game not started")
    if room.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only owner can control turns")
    if not room.timer_enabled:
        raise HTTPException(status_code=400, detail="Timer disabled")
    if not normalize_room_turn_state(room):
        raise HTTPException(status_code=400, detail="Timer disabled")
    if room.turn_state == TURN_STATE_FINISHED:
        raise HTTPException(status_code=400, detail="Игра уже завершена")
    if room.turn_state not in (TURN_STATE_READY_TO_START, TURN_STATE_ACTIVE):
        raise HTTPException(status_code=400, detail="Сначала завершите раздачу ролей")

    room.turn_state = TURN_STATE_ACTIVE
    room.turn_active = True
    if room.turn_started_at is None:
        room.turn_started_at = time.time()

    return room_to_info(room, user_id, username)


@app.post("/api/room/turn/finish", response_model=RoomInfo)
async def room_turn_finish(request: RoomActionRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    touch_room_user(room, user_id)
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        raise HTTPException(status_code=404, detail="Room not found")
    if room.state not in (ROOM_STATE_STARTED, ROOM_STATE_PAUSED):
        raise HTTPException(status_code=400, detail="Game not started")
    if room.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only owner can finish")
    if not room.timer_enabled:
        raise HTTPException(status_code=400, detail="Timer disabled")
    if room.turn_state == TURN_STATE_WAITING:
        raise HTTPException(status_code=400, detail="Сначала запустите игру")

    room.turn_state = TURN_STATE_FINISHED
    room.turn_active = False
    room.turn_started_at = None
    room.turns_completed = True
    return room_to_info(room, user_id, username)


@app.post("/api/room/resume", response_model=RoomInfo)
async def room_resume(request: RoomActionRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only owner can resume")
    if user_id not in room.players:
        raise HTTPException(status_code=403, detail="Not in room")
    touch_room_user(room, user_id)
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        raise HTTPException(status_code=404, detail="Room not found")
    if room.state != ROOM_STATE_PAUSED:
        raise HTTPException(status_code=400, detail="Игра не на паузе")

    room.state = ROOM_STATE_STARTED
    if room.timer_enabled and room.turn_state == TURN_STATE_ACTIVE:
        room.turn_active = True
        room.turn_started_at = time.time()
    set_room_status_message(room, "Игра продолжена")
    return room_to_info(room, user_id, username)


@app.post("/api/room/heartbeat", response_model=RoomInfo)
async def room_heartbeat(request: RoomActionRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    username = normalize_tg_username(user.get("username"))

    room_code = normalizeRoomCode(request.room_code)
    room = rooms.get(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if user_id not in room.players:
        raise HTTPException(status_code=403, detail="Вы вышли из комнаты")

    touch_room_user(room, user_id)
    if drop_stale_room_players(room):
        rooms.pop(room_code, None)
        raise HTTPException(status_code=404, detail="Room not found")
    return room_to_info(room, user_id, username)


@app.post("/api/room/leave", response_model=RoomLeaveResponse)
async def room_leave(request: RoomActionRequest) -> RoomLeaveResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))
    room_code = normalizeRoomCode(request.room_code)

    room = rooms.get(room_code)
    if not room:
        return RoomLeaveResponse(left=True, room_closed=True)
    if user_id not in room.players:
        return RoomLeaveResponse(left=False, room_closed=False)

    remove_room_participant(room, user_id, "вышел из комнаты")
    if not room.players or not real_room_player_ids(room):
        del rooms[room_code]
        return RoomLeaveResponse(left=True, room_closed=True)
    return RoomLeaveResponse(left=True, room_closed=False)


@app.get("/api/cards/image")
def card_image(name: str) -> Response:
    url = get_card_image(name)
    if not url:
        raise HTTPException(status_code=404, detail="Image not found")

    cached = image_cache.get(url)
    now = time.time()
    if cached and now - cached.get("ts", 0) < IMAGE_CACHE_TTL_SECONDS:
        return Response(
            content=cached["content"],
            media_type=cached["content_type"],
            headers={"Cache-Control": "public, max-age=86400"},
        )

    try:
        fetched = fetch_remote_image(url)
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch image")

    image_cache[url] = {"content": fetched["content"], "content_type": fetched["content_type"], "ts": now}
    return Response(
        content=fetched["content"],
        media_type=fetched["content_type"],
        headers={"Cache-Control": "public, max-age=86400"},
    )


def room_to_info(room: RoomSession, user_id: int, username: Optional[str] = None) -> RoomInfo:
    advance_room_turn(room)
    room.turns_completed = room.turn_state == TURN_STATE_FINISHED
    starter_name = None
    if room.state in (ROOM_STATE_STARTED, ROOM_STATE_PAUSED) and room.starter_user_id is not None:
        starter_entry = room.players.get(room.starter_user_id)
        if starter_entry:
            starter_name = str(starter_entry.get("display_name") or "")
    current_turn_name = None
    if room.state in (ROOM_STATE_STARTED, ROOM_STATE_PAUSED) and room.timer_enabled and room.turn_state in (TURN_STATE_READY_TO_START, TURN_STATE_ACTIVE):
        current_turn_user_id = current_room_turn_user_id(room)
    else:
        current_turn_user_id = None
    if current_turn_user_id is not None:
        current_turn_entry = room.players.get(current_turn_user_id)
        if current_turn_entry:
            current_turn_name = str(current_turn_entry.get("display_name") or "")
    return RoomInfo(
        room_code=room.room_code,
        owner_user_id=room.owner_user_id,
        owner_name=room.owner_name,
        host_name=room.owner_name,
        format_mode=room.format_mode,
        play_mode=room.play_mode,
        players=[
            RoomPlayer(
                user_id=str(entry.get("user_id", "")),
                first_name=str(entry.get("first_name")) if entry.get("first_name") is not None else None,
                last_name=str(entry.get("last_name")) if entry.get("last_name") is not None else None,
                display_name=str(entry.get("display_name") or ""),
                isBot=bool(entry.get("is_bot")),
            )
            for entry in room.players.values()
        ],
        player_count=len(room.players),
        player_limit=room.player_limit,
        state=room.state,
        can_start=(room.owner_user_id == user_id and room.state == ROOM_STATE_WAITING and len(room.players) >= MIN_PLAYERS),
        you_are_owner=(room.owner_user_id == user_id),
        starter_name=starter_name,
        timer_enabled=room.timer_enabled,
        turn_time_seconds=room.turn_time_seconds,
        turn_active=room.turn_active,
        turn_state=room.turn_state,
        current_turn_index=room.current_turn_index,
        current_turn_name=current_turn_name,
        turn_started_at=room.turn_started_at,
        turns_completed=room.turns_completed,
        status_message=room.last_status_message,
        can_manage_bots=bool(
            DEV_TOOLS_ENABLED
            and room.state == ROOM_STATE_WAITING
            and room.owner_user_id == user_id
            and is_dev_admin(user_id, username)
        ),
    )


def random_choice(items: List[PlayerId]) -> PlayerId:
    if not items:
        return 0
    return secrets.choice(items)


def log_random(event: str, players: List[PlayerId], spies: List[PlayerId]) -> None:
    if DEBUG_RANDOM:
        print(f"[RANDOM] {event} players={players} spies={spies}")


WEBAPP_DIST = Path(__file__).resolve().parent / "webapp_dist"
if WEBAPP_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEBAPP_DIST), html=True), name="webapp")
