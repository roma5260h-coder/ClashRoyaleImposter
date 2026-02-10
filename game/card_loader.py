"""
Загрузка и управление картами
"""
import json
import random
from typing import List, Optional
from config.settings import CARDS_FILE
from game.models import Card


class CardLoader:
    """Загрузчик карт из JSON"""
    
    _cards_cache: Optional[List[Card]] = None
    
    @classmethod
    def load_cards(cls) -> List[Card]:
        """
        Загрузить карты из файла
        Результат кэшируется для производительности
        """
        if cls._cards_cache is not None:
            return cls._cards_cache
        
        try:
            with open(CARDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Преобразуем JSON в объекты Card
            cls._cards_cache = [
                Card(
                    id=item['id'],
                    name_ru=item['name_ru'],
                    image_url=item['image_url']
                )
                for item in data
            ]
            return cls._cards_cache
        except FileNotFoundError:
            raise Exception(f"Файл карт не найден: {CARDS_FILE}")
        except json.JSONDecodeError:
            raise Exception(f"Ошибка при парсинге JSON: {CARDS_FILE}")
    
    @classmethod
    def get_random_card(cls) -> Card:
        """Получить случайную карту"""
        cards = cls.load_cards()
        if not cards:
            raise Exception("Нет доступных карт")
        return random.choice(cards)
    
    @classmethod
    def get_card_count(cls) -> int:
        """Получить количество доступных карт"""
        return len(cls.load_cards())
