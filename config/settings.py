"""
Конфигурация приложения
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Token
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Пути к файлам
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS_FILE = os.path.join(BASE_DIR, 'data', 'cards.json')

# Логирование
LOG_LEVEL = 'INFO'

# Игра
MIN_PLAYERS = 3
MAX_PLAYERS = 10
DEFAULT_PLAYERS = 4
