"""
agent.py — инициализация LLM, инструментов и AgentExecutor.

Создаёт агента на базе ChatOpenAI (ProxyAPI) с набором инструментов
из tools.py и системным промптом, определяющим поведение бота.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from config import settings
from memory import FileChatMessageHistory
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# ================================================================
# Системный промпт агента
# ================================================================

SYSTEM_PROMPT = """\
Ты — полезный AI-ассистент в Telegram-боте. Твоя задача — помогать \
пользователям, используя доступные инструменты, когда это уместно.

## Правила поведения:
1. Если пользователь задаёт вопрос, на который можно ответить без инструментов — \
отвечай сразу.
2. Если нужен поиск, погода, курс криптовалюты или фиатных валют, QR-код или \
работа с файлами — используй соответствующий инструмент.
3. Если запрос неясен — задай уточняющий вопрос, не пытайся угадать.
4. Отвечай на языке пользователя (русский, если вопрос на русском, иначе — на \
языке вопроса).
5. Если инструмент возвращает ошибку — объясни пользователю, что пошло не так, \
и предложи альтернативу.
6. Будь кратким, но информативным. Не дублируй содержимое результата инструмента \
в ответ — просто сообщи результат.
7. Если задача требует нескольких шагов (например, погода: геокодинг → погода) — \
используй инструменты последовательно.\
"""


# ================================================================
# Создание агента
# ================================================================

def _create_agent() -> AgentExecutor:
    """Создаёт и настраивает AgentExecutor."""

    # Инициализация LLM через ProxyAPI (OpenAI-совместимый формат)
    # gpt-5.x — reasoning-модель, которая на ProxyAPI отклоняет инструменты
    # при включённом reasoning_effort. Явно отключаем reasoning.
    llm = ChatOpenAI(
        model=settings.llm_model,
        openai_api_key=settings.proxyapi_api_key,
        openai_api_base=settings.proxyapi_api_base,
        temperature=settings.llm_temperature,
        reasoning_effort="none",
        streaming=False,
    )

    # Системный промпт
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # Создаём агент с использованием tool calling (OpenAI-native)
    agent = create_tool_calling_agent(
        llm=llm,
        tools=ALL_TOOLS,
        prompt=prompt,
    )

    # Обёртка AgentExecutor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=ALL_TOOLS,
        verbose=False,
        handle_parsing_errors=True,
        max_iterations=10,
        return_intermediate_steps=False,
    )

    return agent_executor


# Кэшируем агента — создаём один раз при импорте
_agent_executor: AgentExecutor | None = None


def get_agent_executor() -> AgentExecutor:
    """Возвращает singleton-экземпляр AgentExecutor."""
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = _create_agent()
    return _agent_executor


def run_agent(user_input: str, chat_id: int | str) -> str:
    """
    Запускает агента для данного user_input и chat_id.

    Использует изолированную память для chat_id, передаёт историю диалога
    в агент и возвращает итоговый ответ.
    """
    agent = get_agent_executor()

    # Создаём историю для этого chat_id
    history = FileChatMessageHistory(chat_id=chat_id)
    history_messages = history.messages

    try:
        # Запускаем агента
        result = agent.invoke({
            "input": user_input,
            "chat_history": history_messages,
        })

        # Сохраняем диалог в историю
        # Добавляем вопрос и ответ агента
        history.add_message(HumanMessage(content=user_input))
        if "output" in result:
            history.add_message(AIMessage(content=result["output"]))

        return result.get("output", "Агент не вернул ответ.")

    except Exception as exc:
        logger.error("Ошибка выполнения агента для chat_id=%s: %s", chat_id, exc, exc_info=True)
        return f"Произошла ошибка при обработке вашего запроса: {exc}"


# Для обратной совместимости — упрощённый интерфейс
def run_agent_sync(user_input: str, chat_id: int | str) -> str:
    """
    Синхронная обёртка для run_agent.

    Вызывает run_agent — внутри AgentExecutor уже выполняется в потоке
    через invoke (не блокирует event loop aiogram).
    """
    return run_agent(user_input, chat_id)
