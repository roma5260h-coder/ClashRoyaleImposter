import random
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum

from game_logic import deal_roles


class GameState(str, Enum):
    """Состояния игровой сессии"""
    IDLE = "idle"
    MODE_SELECTION = "mode_selection"
    PLAYER_COUNT_SELECTION = "player_count_selection"
    ROLE_REVEALING = "role_revealing"
    FINISHED = "finished"


@dataclass
class GameSession:
    """Класс для хранения состояния игровой сессии"""
    
    chat_id: int
    state: GameState = GameState.IDLE
    format_mode: Optional[str] = None
    play_mode: Optional[str] = None
    resolved_random_mode: Optional[str] = None
    player_count: int = 0
    players: List[int] = field(default_factory=list)
    spy_players: List[int] = field(default_factory=list)
    cards_for_players: Dict[int, Optional[str]] = field(default_factory=dict)
    current_player_number: int = 0
    
    def start_new_game(self, format_mode: str, play_mode: str, player_count: int) -> None:
        """Инициализирует новую игру"""
        self.format_mode = format_mode
        self.play_mode = play_mode
        self.player_count = player_count
        self.players = list(range(1, player_count + 1))
        self.spy_players, self.cards_for_players, self.resolved_random_mode = deal_roles(
            self.players,
            play_mode
        )
        self.current_player_number = 1
        self.state = GameState.ROLE_REVEALING
    
    def get_current_player_message(self) -> str:
        """Возвращает сообщение для текущего игрока"""
        return f"🎮 Игрок {self.current_player_number}, нажми кнопку ниже"
    
    def get_role_message(self) -> str:
        """Возвращает сообщение с ролью/картой для текущего игрока"""
        card = None
        if self.cards_for_players:
            card = self.cards_for_players.get(self.current_player_number)
        if card:
            return f"🗺️ Карта: {card}"
        return "🕵️ Ты шпион"
    
    def next_player(self) -> bool:
        """
        Переходит к следующему игроку.
        Возвращает True, если все игроки обработаны, False если есть ещё.
        """
        if self.current_player_number < self.player_count:
            self.current_player_number += 1
            return False
        else:
            self.state = GameState.FINISHED
            return True
    
    def get_game_started_message(self) -> str:
        """Возвращает сообщение о начале игры"""
        starter = random.randint(1, self.player_count)
        return f"✅ Роли розданы!\n🎬 Игру начинает: Игрок {starter}"
