#!/bin/bash

# 🚀 Скрипт быстрого старта Telegram-бота

echo "================================"
echo "🤖 БЫСТРЫЙ СТАРТ БОТА ШПИОН"
echo "================================"
echo ""

# Проверка Python
echo "✅ Проверка Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен!"
    echo "   Установи Python3: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Python версия: $PYTHON_VERSION"

# Проверка requirements.txt
echo ""
echo "✅ Проверка requirements.txt..."
if [ ! -f "requirements.txt" ]; then
    echo "❌ Файл requirements.txt не найден!"
    exit 1
fi
echo "   Найден"

# Установка зависимостей
echo ""
echo "📦 Установка зависимостей..."
python3 -m pip install --upgrade pip > /dev/null 2>&1
python3 -m pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "   ✅ Зависимости установлены"
else
    echo "   ❌ Ошибка при установке зависимостей"
    exit 1
fi

# Проверка .env файла
echo ""
echo "✅ Проверка конфигурации..."

if [ ! -f ".env" ]; then
    echo "   ⚠️  Файл .env не найден"
    echo "   Создаю .env из .env.example..."
    
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "   ✅ Создан .env"
    else
        echo "   ❌ Файл .env.example не найден!"
        exit 1
    fi
fi

# Проверка токена
echo ""
echo "📝 Проверка токена бота..."

TOKEN=$(grep TELEGRAM_BOT_TOKEN .env | cut -d '=' -f 2)

if [ "$TOKEN" = "your_token_here" ] || [ -z "$TOKEN" ]; then
    echo "   ⚠️  ВНИМАНИЕ: Токен не установлен!"
    echo ""
    echo "   1. Откройся к @BotFather в Telegram"
    echo "   2. Выполни /newbot"
    echo "   3. Скопируй токен в .env файл:"
    echo ""
    echo "   TELEGRAM_BOT_TOKEN=твой_токен_здесь"
    echo ""
    read -p "   Установить токен сейчас? (y/n) " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "   Введи токен: " NEW_TOKEN
        
        # Проверка ОС (macOS / Linux / Windows)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/your_token_here/$NEW_TOKEN/" .env
        else
            # Linux
            sed -i "s/your_token_here/$NEW_TOKEN/" .env
        fi
        
        echo "   ✅ Токен сохранён в .env"
    else
        echo "   ⚠️  Не забудь добавить токен перед запуском!"
    fi
else
    echo "   ✅ Токен найден"
fi

# Проверка карт
echo ""
echo "📊 Проверка карт..."

if [ ! -f "data/cards.json" ]; then
    echo "   ❌ Файл data/cards.json не найден!"
    exit 1
fi

CARD_COUNT=$(python3 -c "import json; print(len(json.load(open('data/cards.json'))))" 2>/dev/null)
echo "   ✅ Загружено карт: $CARD_COUNT"

# Запуск бота
echo ""
echo "================================"
echo "🚀 ЗАПУСК БОТА"
echo "================================"
echo ""
echo "Бот запущен и готов к работе!"
echo "Найдите его в Telegram и отправьте /start"
echo ""
echo "Для остановки бота нажмите Ctrl+C"
echo ""

python3 main.py
