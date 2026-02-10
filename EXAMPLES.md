"""
Примеры использования API бота для разработчиков
"""

# ============================================================================
# ПРИМЕР 1: Получение информации о карте
# ============================================================================

from game.card_loader import CardLoader

# Загрузить все карты
cards = CardLoader.load_cards()
print(f"Всего карт: {len(cards)}")

# Получить случайную карту
random_card = CardLoader.get_random_card()
print(f"Карта: {random_card.name_ru}")
print(f"ID: {random_card.id}")
print(f"Изображение: {random_card.image_url}")


# ============================================================================
# ПРИМЕР 2: Создание и управление игрой
# ============================================================================

from game.game_manager import game_manager
from game.models import GameMode, Player, Role

# Создать новую игру
game = game_manager.create_game(
    chat_id=12345,
    creator_id=67890,
    mode=GameMode.STANDARD,
    player_count=4
)

print(f"Создана игра #{game.game_id}")
print(f"Игроков: {len(game.players)}")

# Распределить роли и выбрать карту
game_manager.assign_roles_and_card(game)

print(f"Карта: {game.card.name_ru}")
print(f"Шпион: {game.get_spy().player_id if game.get_spy() else 'Нет'}")
print(f"Граждан: {game.get_citizen_count()}")

# Получить первого игрока (начинает игру)
start_player = game.get_start_player()
print(f"Начинает: Игрок #{start_player.player_id}")


# ============================================================================
# ПРИМЕР 3: Работа с ролями
# ============================================================================

from game.game_manager import RoleDistributor

players = [
    Player(player_id=1, telegram_id=111),
    Player(player_id=2, telegram_id=222),
    Player(player_id=3, telegram_id=333),
    Player(player_id=4, telegram_id=444),
]

# Распределить роли
players_with_roles = RoleDistributor.distribute_roles(players, GameMode.STANDARD)

for player in players_with_roles:
    role_text = RoleDistributor.get_role_message(player.role)
    print(f"Игрок #{player.player_id}: {role_text}")


# ============================================================================
# ПРИМЕР 4: Работа с хранилищем сессий
# ============================================================================

from storage.game_storage import game_storage
from game.models import GameMode

# Получить сессию пользователя
user_id = 67890
session = game_storage.get_session(user_id)

# Заполнить сессию
session.selected_mode = GameMode.STANDARD
session.selected_player_count = 5
session.game_id = 1
session.is_creator = True

print(f"Сессия пользователя {user_id}:")
print(f"  Режим: {session.selected_mode}")
print(f"  Игроков: {session.selected_player_count}")
print(f"  ID игры: {session.game_id}")
print(f"  Создатель: {session.is_creator}")

# Удалить сессию
game_storage.delete_session(user_id)


# ============================================================================
# ПРИМЕР 5: Полный flow игры (синхронно)
# ============================================================================

def create_and_setup_game(chat_id: int, creator_id: int, player_count: int):
    """
    Полный flow создания и настройки игры
    """
    # 1. Создаём игру
    game = game_manager.create_game(
        chat_id=chat_id,
        creator_id=creator_id,
        mode=GameMode.STANDARD,
        player_count=player_count
    )
    
    print(f"✅ Игра создана: #{game.game_id}")
    
    # 2. Распределяем роли и выбираем карту
    game_manager.assign_roles_and_card(game)
    
    print(f"✅ Роли распределены")
    print(f"   Карта: {game.card.name_ru}")
    
    # 3. Выводим информацию о каждом игроке
    for player in game.players:
        if player.role == Role.SPY:
            print(f"   Игрок #{player.player_id}: 🕵️ ШПИОН")
        else:
            print(f"   Игрок #{player.player_id}: 👤 ГРАЖДАНИН")
    
    # 4. Определяем, кто начинает
    start_player = game.get_start_player()
    print(f"✅ Игру начинает: Игрок #{start_player.player_id}")
    
    return game


# Использование
game = create_and_setup_game(
    chat_id=12345,
    creator_id=67890,
    player_count=5
)


# ============================================================================
# ПРИМЕР 6: Создание собственного обработчика
# ============================================================================

async def custom_command_handler(update, context):
    """
    Пример создания собственного обработчика команды
    """
    from handlers.game_handler import send_private_messages
    
    user = update.effective_user
    query = update.callback_query
    
    # Получить сессию пользователя
    session = game_storage.get_session(user.id)
    
    # Получить его игру
    if session.game_id:
        game = game_manager.get_game(session.game_id)
        
        if game:
            # Выполнить какое-то действие
            print(f"Пользователь {user.id} в игре #{game.game_id}")
            
            # Отправить личные сообщения
            # await send_private_messages(game, context)


# ============================================================================
# ПРИМЕР 7: Запросы к API Telegram напрямую
# ============================================================================

async def send_custom_message(chat_id: int, text: str, bot_token: str):
    """
    Отправить сообщение напрямую (без use context)
    """
    from telegram import Bot
    
    bot = Bot(token=bot_token)
    await bot.send_message(chat_id=chat_id, text=text)


# ============================================================================
# ПРИМЕР 8: Тестирование логики распределения ролей
# ============================================================================

def test_role_distribution():
    """
    Тестирование, что ровно 1 шпион в каждой игре
    """
    from game.models import Role
    
    for test_num in range(10):
        players = [
            Player(player_id=i+1, telegram_id=i)
            for i in range(5)
        ]
        
        players = RoleDistributor.distribute_roles(players, GameMode.STANDARD)
        
        spy_count = sum(1 for p in players if p.role == Role.SPY)
        citizen_count = sum(1 for p in players if p.role == Role.CITIZEN)
        
        assert spy_count == 1, f"Ошибка: {spy_count} шпионов вместо 1"
        assert citizen_count == 4, f"Ошибка: {citizen_count} граждан вместо 4"
        
        print(f"✅ Тест {test_num + 1}: OK (1 шпион, 4 гражданина)")


test_role_distribution()


# ============================================================================
# ПРИМЕР 9: Работа с конфигурацией
# ============================================================================

from config.settings import (
    MIN_PLAYERS,
    MAX_PLAYERS,
    CARDS_FILE,
    LOG_LEVEL
)

print(f"Минимум игроков: {MIN_PLAYERS}")
print(f"Максимум игроков: {MAX_PLAYERS}")
print(f"Файл карт: {CARDS_FILE}")
print(f"Уровень логирования: {LOG_LEVEL}")


# ============================================================================
# ПРИМЕР 10: Использование логирования
# ============================================================================

from utils.logger import get_logger

logger = get_logger(__name__)

logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")


# ============================================================================
# ТЕСТЫ
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ API")
    print("=" * 70)
    
    print("\n✅ Все примеры выполнены успешно!")
