import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, quote
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Response
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
INIT_DATA_BYPASS = os.getenv("INIT_DATA_BYPASS", "0") == "1"
DEBUG_RANDOM = os.getenv("DEBUG_RANDOM", "0") == "1"

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


class OfflineStartResponse(BaseModel):
    session_id: str
    current_player_number: int
    player_count: int


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


class RoomJoinRequest(BaseRequest):
    room_code: str
    format_mode: str
    game_mode: str


class RoomActionRequest(BaseRequest):
    room_code: str


class RoomPlayer(BaseModel):
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: str


class RoomInfo(BaseModel):
    room_code: str
    owner_user_id: int
    owner_name: str
    format_mode: str
    play_mode: str
    players: List[RoomPlayer]
    player_count: int
    state: str
    can_start: bool
    you_are_owner: bool
    starter_name: Optional[str] = None


class RoomStartResponse(BaseModel):
    started: bool
    starter_user_id: int
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
    spy_players: List[int] = field(default_factory=list)
    cards_for_players: Dict[int, Optional[str]] = field(default_factory=dict)
    random_allowed_modes: List[str] = field(default_factory=list)
    state: str = "revealing"
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RoomSession:
    room_code: str
    owner_user_id: int
    owner_name: str
    format_mode: str
    play_mode: str = "standard"
    players: Dict[int, Dict[str, Optional[str]]] = field(default_factory=dict)
    resolved_random_mode: Optional[str] = None
    random_allowed_modes: List[str] = field(default_factory=list)
    spy_user_ids: List[int] = field(default_factory=list)
    cards_by_user: Dict[int, Optional[str]] = field(default_factory=dict)
    state: str = "waiting"
    starter_user_id: Optional[int] = None
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
        if now - room.created_at > timedelta(minutes=APP_TTL_MINUTES) and room.state == "waiting":
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


def build_player_entry(user: Dict[str, str], index: int) -> Dict[str, Optional[str]]:
    name = require_display_name(user)
    return {
        "user_id": int(user.get("id", 0)),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "display_name": name,
    }


def build_image_proxy_url(card_name: str) -> Optional[str]:
    if not get_card_image(card_name):
        return None
    return f"/api/cards/image?name={quote(card_name)}"


def fetch_remote_image(url: str) -> Dict[str, object]:
    request = Request(
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


def generate_room_code() -> str:
    for _ in range(5):
        code = uuid.uuid4().hex[:6].upper()
        if code not in rooms:
            return code
    return uuid.uuid4().hex[:8].upper()


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
        spy_players=spies,
        cards_for_players=cards_for_players,
        random_allowed_modes=random_allowed or [],
    )

    return OfflineStartResponse(
        session_id=session_id,
        current_player_number=1,
        player_count=request.player_count,
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

    session.state = "finished"
    starter = random_int(1, session.player_count)
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
    session.state = "revealing"

    return OfflineStartResponse(
        session_id=session.session_id,
        current_player_number=1,
        player_count=session.player_count,
    )


def random_int(start: int, end: int) -> int:
    return secrets.randbelow(end - start + 1) + start


@app.post("/api/room/create", response_model=RoomInfo)
async def room_create(request: RoomCreateRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    if request.format_mode != "online":
        raise HTTPException(status_code=400, detail="Invalid format mode")
    if request.game_mode not in ("standard", "random"):
        raise HTTPException(status_code=400, detail="Invalid game mode")

    random_allowed = request.random_allowed_modes
    if request.game_mode == "random" and random_allowed is not None:
        unique_allowed = list(dict.fromkeys(random_allowed))
        if len(unique_allowed) < 2:
            raise HTTPException(status_code=400, detail="Выберите минимум два режима")
        random_allowed = unique_allowed

    room_code = generate_room_code()
    owner_entry = build_player_entry(user, 1)
    room = RoomSession(
        room_code=room_code,
        owner_user_id=user_id,
        owner_name=owner_entry["display_name"],
        format_mode=request.format_mode,
        play_mode=request.game_mode,
        random_allowed_modes=random_allowed or [],
    )
    room.players[user_id] = owner_entry
    rooms[room_code] = room

    return room_to_info(room, user_id)


@app.post("/api/room/join", response_model=RoomInfo)
async def room_join(request: RoomJoinRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    room = rooms.get(request.room_code.upper())
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if request.format_mode != room.format_mode or request.game_mode != room.play_mode:
        raise HTTPException(status_code=400, detail="Эта комната создана в другом режиме")
    if room.state != "waiting":
        raise HTTPException(status_code=400, detail="Game already started")
    if len(room.players) >= MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Room is full")

    if user_id not in room.players:
        entry = build_player_entry(user, len(room.players) + 1)
        room.players[user_id] = entry

    return room_to_info(room, user_id)


@app.post("/api/room/status", response_model=RoomInfo)
async def room_status(request: RoomActionRequest) -> RoomInfo:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    room = rooms.get(request.room_code.upper())
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return room_to_info(room, user_id)


@app.post("/api/room/start", response_model=RoomStartResponse)
async def room_start(request: RoomActionRequest) -> RoomStartResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    room = rooms.get(request.room_code.upper())
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only owner can start")
    if room.state != "waiting":
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
    room.state = "started"

    starter_user_id = random_choice(players)
    room.starter_user_id = starter_user_id
    starter_entry = room.players.get(starter_user_id)
    starter_name = starter_entry.get("display_name") if starter_entry else ""
    return RoomStartResponse(
        started=True,
        starter_user_id=starter_user_id,
        starter_name=starter_name,
    )


@app.post("/api/room/role", response_model=RoomRoleResponse)
async def room_role(request: RoomActionRequest) -> RoomRoleResponse:
    cleanup_sessions()
    user = verify_init_data(request.initData)
    user_id = int(user.get("id", 0))

    room = rooms.get(request.room_code.upper())
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.state != "started":
        raise HTTPException(status_code=400, detail="Game not started")
    if user_id not in room.players:
        raise HTTPException(status_code=403, detail="Not in room")

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

    room = rooms.get(request.room_code.upper())
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only owner can restart")

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
    room.state = "started"
    room.starter_user_id = random_choice(players)

    starter_entry = room.players.get(room.starter_user_id)
    starter_name = starter_entry.get("display_name") if starter_entry else ""

    return RoomRestartResponse(
        started=True,
        starter_user_id=room.starter_user_id or 0,
        starter_name=starter_name,
    )


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


def room_to_info(room: RoomSession, user_id: int) -> RoomInfo:
    starter_name = None
    if room.state == "started" and room.starter_user_id is not None:
        starter_entry = room.players.get(room.starter_user_id)
        if starter_entry:
            starter_name = starter_entry.get("display_name")
    return RoomInfo(
        room_code=room.room_code,
        owner_user_id=room.owner_user_id,
        owner_name=room.owner_name,
        format_mode=room.format_mode,
        play_mode=room.play_mode,
        players=[
            RoomPlayer(
                user_id=entry["user_id"],
                first_name=entry.get("first_name"),
                last_name=entry.get("last_name"),
                display_name=entry.get("display_name") or "",
            )
            for entry in room.players.values()
        ],
        player_count=len(room.players),
        state=room.state,
        can_start=(room.owner_user_id == user_id and room.state == "waiting" and len(room.players) >= MIN_PLAYERS),
        you_are_owner=(room.owner_user_id == user_id),
        starter_name=starter_name,
    )


def random_choice(items: List[int]) -> int:
    if not items:
        return 0
    return secrets.choice(items)


def log_random(event: str, players: List[int], spies: List[int]) -> None:
    if DEBUG_RANDOM:
        print(f"[RANDOM] {event} players={players} spies={spies}")


WEBAPP_DIST = Path(__file__).resolve().parent / "webapp_dist"
if WEBAPP_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEBAPP_DIST), html=True), name="webapp")
