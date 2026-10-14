"""
run.py — точка входа: инициализация бота aiogram и обработка сообщений.

Бот принимает текстовые сообщения от пользователя, передаёт их агенту
(LangChain AgentExecutor) с изолированной по chat_id памятью и отвечает
в HTML-форматировании.

Агентный вызов выполняется в отдельном потоке (asyncio.to_thread),
чтобы синхронный AgentExecutor не блокировал event loop aiogram.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from agent import run_agent_sync
from config import settings

logger = logging.getLogger(__name__)

# Максимальная длина сообщения в Telegram
TG_MESSAGE_LIMIT = 4096


def _convert_markdown_to_html(text: str) -> str:
    """
    Конвертирует MarkdownV2-разметку в HTML.

    Telegram MarkdownV2 → HTML-теги:
      **bold**    → <b>
      *italic*    → <i>
      __underline__ → <u>
      ~~strikethrough~~ → <s>
      `code`      → <code>
      ```block``` → <pre><code>
    """
    # Блок кода: ``` ... ```
    text = re.sub(r'```(.+?)```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
    # Инлайн-код: ` ... `
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Строчки: ~~ ... ~~
    text = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', text)
    # Подчёркивание: __ ... __
    text = re.sub(r'__([^_]+)__', r'<u>\1</u>', text)
    # Жирный: ** ... **
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    # Курсив: * ... *
    text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)

    return text


# ================================================================
# Хендлеры
# ================================================================

async def handle_start(message: Message) -> None:
    """Приветствие при команде /start."""
    await message.answer(
        "👋 <b>Привет! Я AI-ассистент.</b>\n\n"
        "Я умею:\n"
        "• � <b>Проверить свой сайт</b> — киньте ссылку и получите разбор: "
        "скорость и вес страницы, HTTPS, мобильная версия, заголовок и оффер, "
        "Яндекс.Метрика, формы/телефоны/мессенджеры. "
        "В конце — оценка N/100 и список, с чего начать\n"
        "• �🔎 искать информацию в интернете\n"
        "• 🌤 показывать погоду по городу\n"
        "• 💱 конвертировать криптовалюты и фиатные валюты\n"
        "• 🔲 генерировать QR-коды\n"
        "• 📄 читать и записывать файлы\n\n"
        "Просто напишите мне, что нужно сделать.",
        parse_mode=ParseMode.HTML,
    )


async def handle_message(message: Message, bot: Bot) -> None:
    """Обрабатывает текстовое сообщение: отправляет агенту и отвечает."""
    if not message.text:
        await message.answer(
            "Я понимаю только текстовые сообщения 🙂",
            parse_mode=ParseMode.HTML,
        )
        return

    chat_id = message.chat.id
    user_input = message.text.strip()

    # Индикатор "бот печатает"
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        # Синхронный агент выполняется в отдельном потоке
        answer = await asyncio.to_thread(run_agent_sync, user_input, chat_id)
    except Exception as exc:
        logger.error("Ошибка агента для chat_id=%s: %s", chat_id, exc, exc_info=True)
        await message.answer(
            "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Экранируем HTML-символы, затем конвертируем MarkdownV2 → HTML
    escaped = html.escape(answer)
    safe_answer = _convert_markdown_to_html(escaped)

    # Telegram ограничивает длину сообщения — режем по 4096 символов
    if len(safe_answer) > TG_MESSAGE_LIMIT:
        safe_answer = safe_answer[: TG_MESSAGE_LIMIT - 3] + "..."

    try:
        await message.answer(safe_answer, parse_mode=ParseMode.HTML)
    except Exception as exc:
        # Fallback: если HTML всё же не прошёл — отправляем обычным текстом
        logger.warning("Не удалось отправить HTML-ответ: %s", exc)
        await message.answer(answer, parse_mode=None)


async def handle_unsupported(message: Message) -> None:
    """Реакция на неподдерживаемые типы сообщений."""
    await message.answer(
        "Пока я работаю только с текстом. Напишите сообщение текстом 🙂",
        parse_mode=ParseMode.HTML,
    )


# ================================================================
# Точка входа
# ================================================================

async def main() -> None:
    """Инициализирует бота и запускает long polling."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Приглушаем шумные логи
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    bot = Bot(
        token=settings.tg_bot_api_key,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Регистрация хендлеров
    dp.message.register(handle_start, CommandStart())
    dp.message.register(handle_message, F.text)
    dp.message.register(handle_unsupported, ~F.text)

    logger.info("Бот запущен. Ожидаю сообщения...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
