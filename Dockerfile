FROM node:20-alpine AS webapp-builder
WORKDIR /app/webapp
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci
COPY webapp/ ./
ARG VITE_API_BASE=""
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV RUN_BOT_POLLING=0

COPY backend/requirements.txt ./backend/requirements.txt
COPY bot/requirements.txt ./bot/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r bot/requirements.txt

COPY backend/ ./backend/
COPY bot/ ./bot/
COPY --from=webapp-builder /app/webapp/dist ./backend/webapp_dist

EXPOSE 8080
CMD ["sh", "-c", "if [ \"${RUN_BOT_POLLING:-0}\" = \"1\" ]; then echo \"Starting Telegram bot polling\"; python -m bot.main & else echo \"RUN_BOT_POLLING=0, skip bot polling\"; fi; exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
