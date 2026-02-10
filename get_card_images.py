"""
Скрипт для парсинга картинок карт с Fandom вики Clash Royale
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import json
from typing import Optional, Dict
from collections.abc import Iterable
from data.cards import CARDS

# Словарь для хранения URL картинок
CARD_IMAGES: Dict[str, Dict[str, Optional[str]]] = {}

def get_fandom_image_url(card_name: str) -> Optional[str]:
    """
    Получает URL картинки с Fandom вики для карты
    """
    try:
        # Создаём URL для страницы карты на Fandom
        encoded_name = quote(card_name)
        url = f"https://clash-royale.fandom.com/ru/wiki/{encoded_name}"
        
        # Загружаем страницу
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"❌ {card_name}: страница не найдена (статус {response.status_code})")
            return None
        
        # Парсим HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем изображение карты (обычно первое изображение в статье)
        # На Fandom картинки находятся в тегах <img> внутри divа с классом infobox-image
        img_tag = soup.find('img', {'alt': card_name})
        
        if not img_tag and 'Cards' in card_name:
            # Ищем "Cards [CardName]"
            img_tag = soup.find('img', {'alt': f'Cards {card_name}'})
        
        if not img_tag:
            # Ищем первое изображение в статье
            infobox = soup.find('div', class_='infobox-image')
            if infobox:
                img_tag = infobox.find('img')
        
        if not img_tag:
            # Последняя попытка — первое <img> в основном контенте
            content = soup.find('div', class_='mw-parser-output')
            if content:
                img_tag = content.find('img')
        
        image_url: Optional[str] = None
        if img_tag:
            data_src = img_tag.get("data-src")
            src = img_tag.get("src")

            def _attr_to_str(value: object) -> Optional[str]:
                if value is None:
                    return None
                if isinstance(value, str):
                    return value
                # BeautifulSoup может вернуть AttributeValueList (итерируемый)
                if isinstance(value, Iterable):
                    return " ".join(str(v) for v in value)
                return str(value)

            image_url = _attr_to_str(data_src) or _attr_to_str(src)
            if not image_url:
                srcset_val = _attr_to_str(img_tag.get("srcset"))
                if srcset_val:
                    image_url = srcset_val.split(",")[0].split(" ")[0]
            if image_url and image_url.startswith("//"):
                image_url = f"https:{image_url}"

        if image_url:
            print(f"✅ {card_name}: {image_url}")
            return image_url
        else:
            print(f"⚠️  {card_name}: изображение не найдено на странице")
            return None
            
    except Exception as e:
        print(f"❌ {card_name}: ошибка — {e}")
        return None


def main() -> None:
    """
    Парсит картинки для всех карт и сохраняет результаты
    """
    print("🔄 Начинаем парсинг картинок с Fandom...")
    print(f"📋 Всего карт для обработки: {sum(len(cards) for cards in CARDS.values())}\n")
    
    for category, cards in CARDS.items():
        print(f"\n📂 Категория: {category.upper()}")
        CARD_IMAGES[category] = {}
        
        for card_name in cards:
            image_url = get_fandom_image_url(card_name)
            if image_url:
                CARD_IMAGES[category][card_name] = image_url
            else:
                # Если не нашли, оставляем None
                CARD_IMAGES[category][card_name] = None
    
    # Сохраняем результаты в JSON для проверки
    with open('card_images.json', 'w', encoding='utf-8') as f:
        json.dump(CARD_IMAGES, f, ensure_ascii=False, indent=2)
    
    print("\n✅ Готово! Результаты сохранены в card_images.json")


if __name__ == '__main__':
    main()
