from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List


class RoomState(str, Enum):
    WAITING = "waiting"
    STARTED = "started"


@dataclass
class RoomSession:
    room_code: str
    owner_id: int
    players: Dict[int, str] = field(default_factory=dict)
    state: RoomState = RoomState.WAITING
    format_mode: Optional[str] = None
    play_mode: Optional[str] = None
    resolved_random_mode: Optional[str] = None
    spy_players: List[int] = field(default_factory=list)
    cards_for_players: Dict[int, Optional[str]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    max_players: int = 12

    def add_player(self, user_id: int, display_name: str) -> bool:
        if user_id in self.players:
            return False
        if len(self.players) >= self.max_players:
            return False
        self.players[user_id] = display_name
        return True

    def is_full(self) -> bool:
        return len(self.players) >= self.max_players

    def can_start(self, min_players: int) -> bool:
        return self.state == RoomState.WAITING and len(self.players) >= min_players
