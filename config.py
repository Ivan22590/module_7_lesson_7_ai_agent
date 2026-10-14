"""
config.py — загрузка и валидация переменных окружения.

Использует pydantic-settings для строгой типизации и валидации всех
переменных из .env. При отсутствии обязательных переменных — понятная
ошибка с указанием, что именно пропущено.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Путь к каталогу проекта (родительский каталог config.py)
PROJECT_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Конфигурация приложения из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- Обязательные переменные ----------

    tg_bot_api_key: str = ""
    """Токен Telegram-бота, полученный у @BotFather."""

    proxyapi_api_key: str = ""
    """Ключ ProxyAPI (получить на https://proxyapi.ru)."""

    # ---------- Настройки LLM ----------

    proxyapi_api_base: str = "https://api.proxyapi.ru/v1"
    """Базовый URL ProxyAPI (OpenAI-совместимый эндпоинт)."""

    llm_model: str = "openai/gpt-5.6-luna"
    """Название модели."""

    llm_temperature: float = 0.1
    """Температура генерации (0.0 = детерминированно, 1.0 = креативно)."""

    # ---------- Опциональные переменные (для будущей расширяемости) ----------

    weather_api_key: str = ""
    currency_api_key: str = ""

    # ---------- Пути ----------

    qrcodes_dir: Path = PROJECT_DIR / "qrcodes"
    """Каталог для сгенерированных QR-кодов."""

    def validate(self) -> None:
        """Проверяет наличие обязательных переменных."""
        missing: list[str] = []
        if not self.tg_bot_api_key:
            missing.append("TG_BOT_API_KEY")
        if not self.proxyapi_api_key:
            missing.append("PROXYAPI_API_KEY")
        if missing:
            raise ValueError(
                f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}. "
                f"Создайте .env на основе .env.example и заполните значения."
            )

    def ensure_qrcodes_dir(self) -> None:
        """Создаёт каталог для QR-кодов, если его нет."""
        self.qrcodes_dir.mkdir(parents=True, exist_ok=True)


# Глобальный инстанс конфигурации
settings = Settings()
settings.validate()
settings.ensure_qrcodes_dir()
