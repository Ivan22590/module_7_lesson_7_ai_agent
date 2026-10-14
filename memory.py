"""
memory.py — изолированная по chat_id память диалогов.

Каждый пользователь Telegram получает отдельный файл memory_{chat_id}.json,
чтобы диалоги разных пользователей не пересекались.
Реализует BaseChatMessageHistory из langchain-core.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict

logger = logging.getLogger(__name__)

# Глобальный поток-лок для атомарной записи JSON
_file_lock = threading.Lock()


class FileChatMessageHistory(BaseChatMessageHistory):
    """Сохраняет историю диалогов в JSON-файл с изоляцией по chat_id."""

    def __init__(self, chat_id: int | str, data_dir: Path | None = None) -> None:
        self.chat_id = str(chat_id)
        self.data_dir = data_dir or Path(__file__).resolve().parent
        self._file_path = self.data_dir / f"memory_{self.chat_id}.json"
        self._ensure_file()

    # ---- внутренние методы ----

    def _ensure_file(self) -> None:
        """Создаёт файл с пустым списком сообщений, если его нет."""
        _file_lock.acquire()
        try:
            if not self._file_path.exists():
                self._file_path.write_text("[]", encoding="utf-8")
        finally:
            _file_lock.release()

    def _load_messages(self) -> list[dict[str, Any]]:
        """Загружает сериализованные сообщения из файла."""
        _file_lock.acquire()
        try:
            raw = self._file_path.read_text(encoding="utf-8")
            return json.loads(raw) if raw.strip() else []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Не удалось загрузить файл памяти %s: %s", self._file_path, exc)
            return []
        finally:
            _file_lock.release()

    def _save_messages(self, messages: list[dict[str, Any]]) -> None:
        """Атомарно сохраняет сериализованные сообщения в файл."""
        _file_lock.acquire()
        try:
            self._file_path.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.error("Не удалось сохранить файл памяти %s: %s", self._file_path, exc)
        finally:
            _file_lock.release()

    # ---- публичный интерфейс BaseChatMessageHistory ----

    @property
    def messages(self) -> list[BaseMessage]:
        """Возвращает десериализованные сообщения из истории."""
        raw = self._load_messages()
        return messages_from_dict(raw)

    @messages.setter
    def messages(self, messages: list[BaseMessage]) -> None:
        """Сохраняет сериализованные сообщения в файл."""
        serialized = [message_to_dict(msg) for msg in messages]
        self._save_messages(serialized)

    def add_message(self, message: BaseMessage) -> None:
        """Добавляет одно сообщение в историю и сохраняет."""
        all_messages = self.messages
        all_messages.append(message)
        self.messages = all_messages

    def clear(self) -> list[BaseMessage]:
        """Очищает историю и возвращает пустой список."""
        self._save_messages([])
        return []
