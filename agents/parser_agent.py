"""
agents/parser_agent.py

Parser Agent — первый агент в конвейере ClearMind.

Роль: принимает сырой файл от пользователя (через FastAPI), кодирует в base64,
вызывает MCP сервер (mcp_server/server.py) через стандартный MCP-клиент ADK,
получает обратно нормализованные данные (NormalizedUsageData) и передаёт их
дальше Analyzer Agent'у через A2A протокол.

Этот агент НЕ использует LLM для самого парсинга (парсинг детерминирован —
это просто чтение XML/CSV/JSON). LLM используется только для одной вещи:
если файл не подошёл ни под один формат, агент пытается понять что это
за файл и подсказать пользователю человеческим языком, что не так.
"""

from __future__ import annotations

import base64
import logging
import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

from mcp_server.models import DataSource

logger = logging.getLogger("clearmind.parser_agent")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


# ──────────────────────────────────────────────────────────────────
# Подключение к MCP серверу
# ──────────────────────────────────────────────────────────────────


def build_mcp_toolset() -> MCPToolset:
    """
    Создаёт набор инструментов из нашего MCP сервера (mcp_server/server.py).

    ADK запускает MCP сервер как дочерний процесс через stdio и автоматически
    регистрирует его tools (в нашем случае один — parse_usage_export) как
    функции, которые агент может вызывать.
    """
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="python",
                args=["-m", "mcp_server.server"],
            )
        )
    )


# ──────────────────────────────────────────────────────────────────
# Вспомогательная функция, которую агент вызывает напрямую (не через LLM)
# для типичного случая — когда тип файла уже известен с фронтенда
# ──────────────────────────────────────────────────────────────────


def encode_file_for_mcp(raw_bytes: bytes) -> str:
    """Кодирует сырые байты файла в base64 строку для передачи через MCP tool."""
    return base64.b64encode(raw_bytes).decode("ascii")


def detect_source_from_filename(filename: str) -> DataSource | None:
    """
    Простая эвристика определения формата по имени/расширению файла —
    используется фронтендом до вызова агента, чтобы сразу показать
    пользователю правильную подсказку (если файл явно не тот формат).
    """
    lowered = filename.lower()
    if lowered.endswith(".xml") and "screentime" in lowered:
        return DataSource.APPLE_SCREEN_TIME
    if lowered.endswith(".csv"):
        return DataSource.GOOGLE_DIGITAL_WELLBEING
    if "tiktok" in lowered and lowered.endswith(".json"):
        return DataSource.TIKTOK_EXPORT
    if "instagram" in lowered and lowered.endswith(".json"):
        return DataSource.INSTAGRAM_EXPORT
    return None


# ──────────────────────────────────────────────────────────────────
# Системный промпт агента
# ──────────────────────────────────────────────────────────────────

PARSER_AGENT_INSTRUCTION = """\
Ты — Parser Agent в системе ClearMind. Твоя единственная задача —
правильно вызвать инструмент `parse_usage_export` с корректным `source`
и base64-содержимым файла, который тебе передали.

Правила:
1. Если пользователь явно указал тип файла (screen time / digital wellbeing /
   tiktok / instagram) — используй его как `source`.
2. Если тип неясен — посмотри на структуру: XML начинается с `<`, CSV содержит
   запятые и заголовок строкой, JSON начинается с `{`.
3. После вызова инструмента верни результат КАК ЕСТЬ, без интерпретации —
   интерпретацией паттернов занимается Analyzer Agent, не ты.
4. Если парсинг не удался (success: false) — объясни пользователю простым
   языком что не так с файлом и как экспортировать данные правильно.
5. Никогда не пытайся "угадать" или сгенерировать данные, если парсинг
   не удался. Только реальные распарсенные данные.
"""


def build_parser_agent() -> Agent:
    """
    Собирает Parser Agent с подключённым MCP toolset.

    google.adk.agents.Agent — базовый класс ADK для LLM-агента с инструментами.
    Когда пользователь присылает файл, агент решает как его обработать и
    вызывает parse_usage_export через MCP.
    """
    toolset = build_mcp_toolset()

    agent = Agent(
        name="parser_agent",
        model=GEMINI_MODEL,
        instruction=PARSER_AGENT_INSTRUCTION,
        tools=[toolset],
        description=(
            "Агент, который читает экспорты данных об использовании устройства "
            "(Screen Time, Digital Wellbeing, TikTok, Instagram) через MCP сервер "
            "и возвращает нормализованные данные."
        ),
    )
    return agent


# Singleton-экземпляр агента — переиспользуется внутри одного процесса
_parser_agent_instance: Agent | None = None


def get_parser_agent() -> Agent:
    """Возвращает (создавая при первом вызове) экземпляр Parser Agent."""
    global _parser_agent_instance
    if _parser_agent_instance is None:
        logger.info("Инициализация Parser Agent...")
        _parser_agent_instance = build_parser_agent()
    return _parser_agent_instance