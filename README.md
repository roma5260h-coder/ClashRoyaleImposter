# 🕵️ Spy Game — Telegram Bot + Mini App

Теперь игра «Шпион» работает как **Telegram Mini App** с серверной логикой на backend. Бот нужен только для запуска Mini App.

## ✅ Что умеет

- Форматы игры:
  - Офлайн (один телефон по кругу)
  - Онлайн (комнаты по коду)
- Режимы:
  - Стандартный
  - Рандом (системный выбор сценария)
- Рандом‑сценарии:
  - Все шпионы
  - У всех одна карта
  - У всех разные карты
  - Несколько шпионов (если игроков > 3)
- Карты локальные, на русском

## 📁 Структура репозитория

```
ClashRoyalBot/
├── bot/                # Телеграм-бот (кнопка открыть Mini App)
├── backend/            # FastAPI backend (логика игры и сессий)
├── webapp/             # Mini App (React + Vite)
├── data/               # Список карт (локально)
├── .env.example
└── README.md
```

## ⚙️ Переменные окружения

Скопируй `.env.example` в `.env` и заполни:

```
BOT_TOKEN=123456789:ABCdefGHIjklmNOPqrsTUVwxyZ
WEBAPP_URL=https://your-domain.tld
WEBAPP_ORIGINS=https://your-domain.tld,http://localhost:5173
INIT_DATA_BYPASS=0
ROOM_DEBUG=0
APP_ENV=production
DEV_TOOLS_ENABLED=0
DEV_ADMIN_IDS=123456789
DEV_ADMIN_USERNAMES=gerafen
```

`INIT_DATA_BYPASS=1` — только для локальной разработки, отключает проверку подписи initData.
`ROOM_DEBUG=1` или `APP_ENV=dev` — включает диагностические логи create/join по комнатам.
`DEV_TOOLS_ENABLED=1` + `DEV_ADMIN_IDS`/`DEV_ADMIN_USERNAMES` — включает DEV endpoints для добавления/очистки ботов в лобби (только хост и только для указанных Telegram ID/username).

## 🚀 Запуск backend

```bash
cd /Users/nikita/Desktop/ClashRoyalBot/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# из корня проекта (чтобы .env считался)
cd /Users/nikita/Desktop/ClashRoyalBot
uvicorn backend.main:app --reload --port 8000 --workers 1
```

Важно для online-комнат с in-memory storage:
- держи `workers=1`;
- в Railway выставь `replicas=1` для этого сервиса, иначе create/join может попадать в разные инстансы.

## 🧩 Запуск Mini App (React)

```bash
cd /Users/nikita/Desktop/ClashRoyalBot/webapp
npm install
cat > .env <<'EOF'
VITE_API_BASE=http://localhost:8000
EOF
npm run dev
```

Открой `http://localhost:5173` в браузере. Для Telegram нужен HTTPS.
DEV доступ к скрытому меню определяется backend (по `DEV_TOOLS_ENABLED` + `DEV_ADMIN_IDS`/`DEV_ADMIN_USERNAMES`), фронтенду отдельные DEV admin переменные не нужны.

## 🤖 Запуск бота

```bash
cd /Users/nikita/Desktop/ClashRoyalBot/bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# из корня проекта (чтобы .env считался)
cd /Users/nikita/Desktop/ClashRoyalBot
python3 bot/main.py
```

## 🔒 HTTPS для Telegram WebApp

Telegram требует HTTPS. Быстрый вариант — туннель:

### ngrok
```bash
ngrok http 5173
```
Скопируй выданный `https://...` и вставь в `WEBAPP_URL`.

### cloudflared
```bash
cloudflared tunnel --url http://localhost:5173
```

## ✅ Сценарии для проверки

- Офлайн + стандартный
- Офлайн + рандом
- Онлайн + стандартный
- Онлайн + рандом
- Ошибки: неверный код, мало игроков, старт не владельцем
- DEV: в online-лобби хост-админ может открыть скрытую панель (кнопка `⋯` или 5 тапов по коду комнаты) и добавить тестовых `🤖 Bot N`

## 🛠️ Технологии

- **Bot**: aiogram 3.x
- **Backend**: FastAPI
- **Mini App**: React + Vite

---

Если нужно, добавлю WebSocket для онлайна или Redis для хранения сессий.
