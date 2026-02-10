# 📚 Гайд по расширению функционала

Этот документ объясняет, как расширять бота с новыми функциями.

## 1️⃣ Добавление новых режимов игры

### Шаг 1: Добавь новый режим в enum

**Файл: `game/models.py`**

```python
class GameMode(Enum):
    STANDARD = "standard"     # Существующий режим
    DOUBLE_SPY = "double_spy" # Новый режим: 2 шпиона
```

### Шаг 2: Добавь логику распределения ролей

**Файл: `game/game_manager.py`** (метод `RoleDistributor.distribute_roles`)

```python
if game_mode == GameMode.DOUBLE_SPY:
    # Выбираем 2 шпионов
    spy_indices = random.sample(range(len(players_copy)), 2)
    for i, player in enumerate(players_copy):
        if i in spy_indices:
            player.role = Role.SPY
        else:
            player.role = Role.CITIZEN
```

### Шаг 3: Добавь кнопку в UI

**Файл: `keyboards/inline_keyboards.py`**

```python
def game_mode_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📋 Стандартный режим", callback_data="mode_standard")],
        [InlineKeyboardButton("👥 Двойной шпион", callback_data="mode_double_spy")]
    ]
    return InlineKeyboardMarkup(buttons)
```

### Шаг 4: Добавь обработчик

**Файл: `handlers/game_mode_handler.py`**

```python
async def mode_double_spy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... аналогично mode_standard_callback
```

**Файл: `main.py`**

```python
app.add_handler(
    CallbackQueryHandler(mode_double_spy_callback, pattern="^mode_double_spy$")
)
```

---

## 2️⃣ Добавление таймера для подсказок

### Использование APScheduler

```bash
pip install APScheduler
```

**Новый файл: `game/timer.py`**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

class GameTimer:
    def __init__(self, game_id: int, duration: int = 60):
        self.game_id = game_id
        self.duration = duration
        self.scheduler = AsyncIOScheduler()
    
    async def start_round(self, callback):
        """Запустить раунд с таймером"""
        self.scheduler.add_job(
            callback,
            'interval',
            seconds=1,
            args=[self.game_id],
            id=f'round_{self.game_id}'
        )
        self.scheduler.start()
```

**В `handlers/game_handler.py`:**

```python
async def player_count_callback(update, context):
    # ... существующий код ...
    
    # Добавляем таймер
    timer = GameTimer(game.game_id, duration=60)
    await timer.start_round(on_timer_tick)
```

---

## 3️⃣ Добавление голосования на выбывание

**Новый файл: `game/voting.py`**

```python
from typing import Dict, List

class VotingManager:
    def __init__(self, game_id: int):
        self.game_id = game_id
        self.votes: Dict[int, int] = {}  # player_id -> voted_for_player_id
    
    def add_vote(self, voter_id: int, target_id: int) -> None:
        """Добавить голос"""
        self.votes[voter_id] = target_id
    
    def get_results(self) -> Dict[int, int]:
        """Получить результаты голосования"""
        from collections import Counter
        return Counter(self.votes.values())
    
    def get_eliminated(self) -> int:
        """Получить выбывшего игрока"""
        results = self.get_results()
        if results:
            return max(results, key=results.get)
        return None
```

**В handlers:**

```python
async def voting_handler(update, context):
    game_id = context.user_data.get('game_id')
    voting = VotingManager(game_id)
    
    # Собираем голоса
    # Выбываем игрока с максимум голосов
```

---

## 4️⃣ Добавление новых карт

### Просто отредактируй `data/cards.json`:

```json
[
  {"id": "existing_card", "name_ru": "Существующая карта", "image_url": "..."},
  {"id": "new_card", "name_ru": "Новая карта", "image_url": "https://..."}
]
```

Карты загружаются **автоматически** при запуске!

---

## 5️⃣ Добавление статистики игрока

**Новый файл: `storage/player_stats.py`**

```python
import json
from typing import Dict

class PlayerStats:
    def __init__(self, filepath: str = "data/stats.json"):
        self.filepath = filepath
        self.stats = self._load_stats()
    
    def _load_stats(self) -> Dict:
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def update_stats(self, user_id: int, role: str, won: bool) -> None:
        """Обновить статистику игрока"""
        if user_id not in self.stats:
            self.stats[user_id] = {'wins': 0, 'losses': 0}
        
        if won:
            self.stats[user_id]['wins'] += 1
        else:
            self.stats[user_id]['losses'] += 1
        
        self._save_stats()
    
    def _save_stats(self) -> None:
        with open(self.filepath, 'w') as f:
            json.dump(self.stats, f, indent=2)
```

---

## 6️⃣ Добавление команды `/stats`

**Файл: `handlers/stats_handler.py`**

```python
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику игрока"""
    user_id = update.effective_user.id
    
    from storage.player_stats import PlayerStats
    stats = PlayerStats()
    
    if user_id not in stats.stats:
        await update.message.reply_text("Ты ещё не играл!")
        return
    
    player_stat = stats.stats[user_id]
    total = player_stat['wins'] + player_stat['losses']
    
    text = (
        f"📊 Твоя статистика:\n\n"
        f"✅ Побед: {player_stat['wins']}\n"
        f"❌ Поражений: {player_stat['losses']}\n"
        f"🎮 Всего игр: {total}"
    )
    
    await update.message.reply_text(text)
```

**В `main.py`:**

```python
from handlers.stats_handler import stats_command

app.add_handler(CommandHandler("stats", stats_command))
```

---

## 7️⃣ Добавление многоязычности

**Новый файл: `utils/i18n.py`**

```python
TRANSLATIONS = {
    'en': {
        'spy': 'You are the spy!',
        'citizen': 'You are a citizen!',
    },
    'ru': {
        'spy': 'Ты шпион!',
        'citizen': 'Ты обычный игрок!',
    }
}

def get_message(key: str, lang: str = 'ru') -> str:
    return TRANSLATIONS.get(lang, {}).get(key, '')
```

---

## 8️⃣ Добавление базы данных

Вместо памяти можно использовать **SQLite** или **PostgreSQL**:

```bash
pip install sqlalchemy
```

**Новый файл: `storage/database.py`**

```python
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
engine = create_engine('sqlite:///game.db')

class UserModel(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    wins = Column(Integer, default=0)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
```

---

## 📝 Принципы проектирования

1. **Модульность** — каждый модуль отвечает за одну функцию
2. **Расширяемость** — легко добавлять новые режимы и функции
3. **Чистота кода** — понятные имена переменных, docstring'и
4. **Отделение логики** — бизнес-логика отдельно от обработчиков
5. **Кэширование** — загружаем карты один раз при запуске

---

## 🚀 Очередь функций для добавления

- [ ] Таймер для раундов
- [ ] Голосование на выбывание
- [ ] Статистика игроков
- [ ] Режим "2 шпиона"
- [ ] Сохранение в БД
- [ ] Многоязычность
- [ ] Админ-панель
- [ ] Рейтинговая система

---

**Удачи в разработке! 🎉**
