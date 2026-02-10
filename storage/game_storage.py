"""
Хранилище состояния пользовательских сессий
"""
from typing import Optional, Dict
from game.models import GameMode


class UserSession:
    """Состояние сессии пользователя"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.game_id: Optional[int] = None
        self.selected_mode: Optional[GameMode] = None
        self.selected_player_count: Optional[int] = None
        self.is_creator: bool = False


class GameStorage:
    """Хранилище пользовательских сессий"""
    
    def __init__(self):
        self._sessions: Dict[int, UserSession] = {}
    
    def get_session(self, user_id: int) -> UserSession:
        """Получить сессию пользователя"""
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(user_id)
        return self._sessions[user_id]
    
    def create_session(self, user_id: int) -> UserSession:
        """Создать новую сессию"""
        session = UserSession(user_id)
        self._sessions[user_id] = session
        return session
    
    def delete_session(self, user_id: int) -> None:
        """Удалить сессию"""
        if user_id in self._sessions:
            del self._sessions[user_id]
    
    def clear_all(self) -> None:
        """Очистить все сессии"""
        self._sessions.clear()


# Глобальное хранилище
game_storage = GameStorage()
