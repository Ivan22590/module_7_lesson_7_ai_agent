# ============================================================
# Dockerfile для Telegram AI-агента (aiogram + LangChain)
# Сборка: docker build -t tg-ai-agent .
# Запуск: docker compose up -d --build
# ============================================================

FROM python:3.11-slim

# Не буферизировать вывод — логи сразу попадают в docker logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Сначала зависимости отдельным слоем — для кэширования сборки
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Затем код приложения
COPY . .

# Запуск от непривилегированного пользователя
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "run.py"]
