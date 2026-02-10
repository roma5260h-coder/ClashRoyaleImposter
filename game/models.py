"""
Модели данных для игры Шпион
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class Role(Enum):
    """Роли в игре"""
    SPY = "spy"              # Шпион (не знает карту)
    CITIZEN = "citizen"      # Обычный игрок (знает карту)


class GameMode(Enum):
    """Режимы игры"""
    STANDARD = "standard"    # Стандартный: 1 шпион, остальные знают карту


class GameStatus(Enum):
    """Состояния жизненного цикла игры"""
    LOBBY = "lobby"
    READY = "ready"
    PLAYING = "playing"
    FINISHED = "finished"


@dataclass
class Player:
    """Модель игрока"""
    player_id: int           # Номер игрока в игре (1, 2, 3...)
    telegram_id: int         # Telegram ID пользователя
    role: Optional[Role] = None
    username: Optional[str] = None


@dataclass
class Card:
    """Модель карты"""
    id: str                  # Уникальный ID карты
    name_ru: str            # Название на русском
    image_url: str          # URL изображения


@dataclass
class Game:
    """Модель игровой сессии"""
    game_id: int             # Уникальный ID игры
    chat_id: int             # ID чата, где началась игра
    creator_id: int          # Telegram ID создателя игры
    mode: GameMode           # Режим игры
    players: List[Player]    # Список игроков
    card: Optional[Card] = None      # Выбранная карта
    status: GameStatus = GameStatus.LOBBY
    is_card_modal_open: bool = False
    joined_player_ids: set[int] = field(default_factory=set)
    card_closed_player_ids: set[int] = field(default_factory=set)
    
    def get_spy(self) -> Optional[Player]:
        """Получить шпиона"""
        for player in self.players:
            if player.role == Role.SPY:
                return player
        return None
    
    def get_citizen_count(self) -> int:
        """Количество обычных игроков"""
        return sum(1 for p in self.players if p.role == Role.CITIZEN)
    
    def get_start_player(self) -> Optional[Player]:
        """Первый игрок, начинающий раунд"""
        if not self.players:
            return None
        return self.players[0]

    def all_players_joined(self) -> bool:
        """Проверить, что все слоты игроков заняты"""
        return len(self.joined_player_ids) >= len(self.players)

    def all_players_closed_card(self) -> bool:
        """Проверить, что все игроки закрыли карточку"""
        return len(self.card_closed_player_ids) >= len(self.players)
