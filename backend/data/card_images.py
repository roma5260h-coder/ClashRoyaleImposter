import json
from pathlib import Path
from typing import Dict, Optional


_CARD_IMAGES: Dict[str, Dict[str, Optional[str]]] = {}


def _load_card_images() -> Dict[str, Dict[str, Optional[str]]]:
    if _CARD_IMAGES:
        return _CARD_IMAGES

    json_path = Path(__file__).resolve().with_name("card_images.json")
    try:
        with json_path.open("r", encoding="utf-8") as f:
            _CARD_IMAGES.update(json.load(f))
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        pass

    return _CARD_IMAGES


def get_card_image(card_name: str) -> Optional[str]:
    data = _load_card_images()
    for cards in data.values():
        url = cards.get(card_name)
        if url and isinstance(url, str) and url.startswith("http"):
            return url
    return None
