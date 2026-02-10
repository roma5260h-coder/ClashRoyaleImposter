#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "${ROOT_DIR}/.env" ]; then
  echo "❌ .env not found in project root (${ROOT_DIR})." >&2
  echo "Copy .env.example to .env and fill BOT_TOKEN, WEBAPP_URL." >&2
  exit 1
fi

export $(grep -v '^#' "${ROOT_DIR}/.env" | xargs)

echo "✅ Project root: ${ROOT_DIR}"

# Check npm
if ! command -v npm >/dev/null 2>&1; then
  echo "❌ npm not found. Install Node.js first (e.g. 'brew install node' or via nvm)." >&2
  exit 1
fi

# Backend venv
if [ ! -d "${ROOT_DIR}/backend/.venv" ]; then
  echo "⚙️  Creating backend venv..."
  python3 -m venv "${ROOT_DIR}/backend/.venv"
fi
source "${ROOT_DIR}/backend/.venv/bin/activate"
pip install -q -r "${ROOT_DIR}/backend/requirements.txt"

deactivate

# Ensure backend card images json exists
if [ -f "${ROOT_DIR}/card_images.json" ] && [ ! -f "${ROOT_DIR}/backend/data/card_images.json" ]; then
  cp "${ROOT_DIR}/card_images.json" "${ROOT_DIR}/backend/data/card_images.json"
fi

# Bot venv
if [ ! -d "${ROOT_DIR}/bot/.venv" ]; then
  echo "⚙️  Creating bot venv..."
  python3 -m venv "${ROOT_DIR}/bot/.venv"
fi
source "${ROOT_DIR}/bot/.venv/bin/activate"
pip install -q -r "${ROOT_DIR}/bot/requirements.txt"

deactivate

# Webapp deps
if [ ! -d "${ROOT_DIR}/webapp/node_modules" ]; then
  echo "⚙️  Installing webapp deps..."
  (cd "${ROOT_DIR}/webapp" && npm install)
fi

# Ensure webapp .env
if [ ! -f "${ROOT_DIR}/webapp/.env" ]; then
  echo "VITE_API_BASE=http://localhost:8000" > "${ROOT_DIR}/webapp/.env"
fi

# Run processes
echo "🚀 Starting backend on :8000"
source "${ROOT_DIR}/backend/.venv/bin/activate"
uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!

deactivate

echo "🚀 Starting webapp on :5173"
(cd "${ROOT_DIR}/webapp" && npm run dev -- --host 0.0.0.0) &
WEBAPP_PID=$!

echo "🚀 Starting bot"
source "${ROOT_DIR}/bot/.venv/bin/activate"
python3 "${ROOT_DIR}/bot/main.py" &
BOT_PID=$!

deactivate

trap "echo '🛑 Stopping...'; kill $BACKEND_PID $WEBAPP_PID $BOT_PID" EXIT

wait
