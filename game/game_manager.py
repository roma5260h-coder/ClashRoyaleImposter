"""
Распределение ролей и управление состоянием игры
"""
import random
from typing import List, Optional, Union
from game.models import Player, Role, GameMode, Game, GameStatus
from game.card_loader import CardLoader


class RoleDistributor:
    """Распределение ролей между игроками"""
    
    @staticmethod
    def distribute_roles(players: List[Player], game_mode: GameMode) -> List[Player]:
        """
        Распределить роли игрокам случайным образом
        
        Args:
            players: Список игроков без ролей
            game_mode: Режим игры
        
        Returns:
            Список игроков с назначенными ролями
        """
        # Копируем список, чтобы не изменять оригинал
        players_copy = players.copy()
        
        if game_mode == GameMode.STANDARD:
            # Стандартный режим: 1 шпион, остальные — обычные игроки
            spy_index = random.randint(0, len(players_copy) - 1)
            
            for i, player in enumerate(players_copy):
                if i == spy_index:
                    player.role = Role.SPY
                else:
                    player.role = Role.CITIZEN
        
        return players_copy
    
    @staticmethod
    def get_role_message(role: Role) -> str:
        """Получить текст сообщения для роли"""
        if role == Role.SPY:
            return "🕵️ Ты шпион!"
        elif role == Role.CITIZEN:
            return "👤 Ты обычный игрок"
        return ""


class GameManager:
    """Менеджер игровых сессий"""
    
    def __init__(self):
        """Инициализация менеджера"""
        self.games: dict[int, Game] = {}
        self._game_counter = 0
    
    def create_game(self, chat_id: int, creator_id: int, 
                   mode: GameMode, player_count: int) -> Game:
        """
        Создать новую игру
        
        Args:
            chat_id: ID чата
            creator_id: Telegram ID создателя
            mode: Режим игры
            player_count: Количество игроков
        
        Returns:
            Объект новой игры
        """
        self._game_counter += 1
        game_id = self._game_counter
        
        # Создаём пустой список игроков с номерами
        players = [
            Player(player_id=i+1, telegram_id=0)
            for i in range(player_count)
        ]
        
        game = Game(
            game_id=game_id,
            chat_id=chat_id,
            creator_id=creator_id,
            mode=mode,
            players=players,
            status=GameStatus.LOBBY
        )
        
        self.games[game_id] = game
        return game
    
    def get_game(self, game_id: Union[int, str]) -> Optional[Game]:
        """Получить игру по ID (поддерживает int и str)"""
        try:
            normalized_game_id = int(game_id)
        except (TypeError, ValueError):
            return None
        return self.games.get(normalized_game_id)
    
    def assign_roles_and_card(self, game: Game) -> None:
        """
        Назначить роли игрокам и выбрать карту
        
        Args:
            game: Объект игры
        """
        # Распределяем роли
        game.players = RoleDistributor.distribute_roles(game.players, game.mode)
        
        # Выбираем карту
        game.card = CardLoader.get_random_card()
        
        # Обновляем статус
        game.status = GameStatus.READY
        game.is_card_modal_open = False
        game.card_closed_player_ids.clear()

    def mark_player_joined(self, game: Game, player_id: int) -> None:
        """Отметить, что слот игрока в лобби заполнен"""
        if 1 <= player_id <= len(game.players):
            game.joined_player_ids.add(player_id)

    def mark_all_players_joined(self, game: Game) -> None:
        """Отметить всех игроков присоединившимися (упрощённый режим)"""
        for player in game.players:
            game.joined_player_ids.add(player.player_id)

    def can_start_game(self, game: Game) -> bool:
        """Проверка, можно ли безопасно стартовать игру"""
        return (
            game.status in {GameStatus.LOBBY, GameStatus.READY}
            and game.card is not None
            and game.all_players_joined()
        )

    def start_game(self, game: Game) -> bool:
        """
        Запустить игру:
        - нельзя запускать в FINISHED
        - нельзя запускать, если не заполнено лобби
        - при старте открывается модалка карты
        """
        if game.status == GameStatus.FINISHED:
            return False

        if game.card is None or any(player.role is None for player in game.players):
            self.assign_roles_and_card(game)

        if not self.can_start_game(game):
            game.status = GameStatus.READY
            return False

        game.status = GameStatus.PLAYING
        game.is_card_modal_open = True
        game.card_closed_player_ids.clear()
        return True

    def close_card_for_player(self, game: Game, player_id: int) -> bool:
        """
        Закрыть карточку для конкретного игрока (по slot/player_id).
        Возвращает True, если карточка закрыта всеми игроками.
        """
        if 1 <= player_id <= len(game.players):
            game.card_closed_player_ids.add(player_id)

        if game.all_players_closed_card():
            game.is_card_modal_open = False
            return True
        return False

    def finish_game(self, game: Game) -> bool:
        """
        Завершить игру только в корректном состоянии.
        Игра не может завершиться, пока открыта карточка карты.
        """
        if game.status != GameStatus.PLAYING:
            return False
        if game.is_card_modal_open:
            return False

        game.status = GameStatus.FINISHED
        return True
    
    def delete_game(self, game_id: int) -> None:
        """Удалить игру"""
        if game_id in self.games:
            del self.games[game_id]


# Глобальный экземпляр менеджера игр
game_manager = GameManager()
