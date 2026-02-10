"""
Логирование (опционально, для отладки)
"""
import logging
from config.settings import LOG_LEVEL

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

# Handler для вывода в консоль
handler = logging.StreamHandler()
handler.setLevel(LOG_LEVEL)

# Формат логов
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер с указанным именем
    
    Args:
        name: Имя логгера (обычно __name__)
    
    Returns:
        Логгер
    """
    return logging.getLogger(name)
