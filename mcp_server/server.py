"""
mcp_server/server.py

MCP (Model Context Protocol) сервер ClearMind.

Этот сервер предоставляет агентам ОДИН инструмент: parse_usage_export.
Агент (Parser Agent) вызывает его через MCP, передавая байты файла
и тип источника — сервер возвращает нормализованные данные.

Ключевой принцип безопасности: сервер НИЧЕГО не пишет на диск и не делает
исходящих сетевых запросов. Файл существует только в памяти процесса
на время вызова tool'а. Это то, что Guard Agent впоследствии верифицирует.

Запуск:
    python -m mcp_server.server
    # или
    clearmind-mcp
"""

from __future__ import annotations

import base64
import logging
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_server.models import DataSource
from mcp_server.parsers import parse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("clearmind.mcp_server")

# Создаём MCP сервер с именем — это имя увидят клиенты (наши агенты)
app = Server("clearmind-data-parser")

# Лимит на размер файла — защита от DoS и от случайной загрузки чего-то огромного.
# Берётся из .env, дефолт 10 MB.
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_BYTES", "10485760"))


@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    MCP вызывает этот метод чтобы узнать, какие инструменты доступны.
    Agent Development Kit (ADK) на стороне Parser Agent читает эту схему
    и автоматически понимает как вызывать наш tool.
    """
    return [
        Tool(
            name="parse_usage_export",
            description=(
                "Парсит экспорт данных об использовании устройства в нормализованный "
                "формат. Поддерживает форматы: Apple Screen Time (XML), Google Digital "
                "Wellbeing (CSV), TikTok export (JSON), Instagram export (JSON). "
                "Файл передаётся как base64-строка и обрабатывается только в памяти — "
                "ничего не сохраняется на диск."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": [s.value for s in DataSource],
                        "description": "Тип источника данных",
                    },
                    "file_content_base64": {
                        "type": "string",
                        "description": "Содержимое файла, закодированное в base64",
                    },
                },
                "required": ["source", "file_content_base64"],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Главный обработчик вызовов инструментов.
    Parser Agent вызывает parse_usage_export с base64-данными файла.
    """
    if name != "parse_usage_export":
        return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]

    source_raw = arguments.get("source")
    file_b64 = arguments.get("file_content_base64")

    if not source_raw or not file_b64:
        return [
            TextContent(
                type="text",
                text='{"success": false, "error_message": "Не переданы source или file_content_base64"}',
            )
        ]

    # Декодируем base64 — это единственное место где файл существует как bytes
    try:
        raw_bytes = base64.b64decode(file_b64)
    except Exception as exc:
        return [
            TextContent(
                type="text",
                text=f'{{"success": false, "error_message": "Ошибка декодирования base64: {exc}"}}',
            )
        ]

    # Guard-проверка прямо в MCP сервере: размер файла
    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        return [
            TextContent(
                type="text",
                text=(
                    f'{{"success": false, "error_message": '
                    f'"Файл превышает лимит {MAX_FILE_SIZE_BYTES} байт"}}'
                ),
            )
        ]

    try:
        source = DataSource(source_raw)
    except ValueError:
        return [
            TextContent(
                type="text",
                text=f'{{"success": false, "error_message": "Неизвестный source: {source_raw}"}}',
            )
        ]

    logger.info("Парсинг файла источника=%s, размер=%d байт", source.value, len(raw_bytes))

    result = parse(source, raw_bytes)

    # raw_bytes выходит из области видимости здесь и будет собран GC —
    # файл нигде не сохраняется и не логируется в открытом виде
    logger.info(
        "Результат парсинга: success=%s, rows=%d, warnings=%d",
        result.success,
        result.rows_parsed,
        len(result.warnings),
    )

    return [TextContent(type="text", text=result.model_dump_json())]


async def run_server() -> None:
    """Запускает MCP сервер поверх stdio — стандартный транспорт для ADK агентов."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    """Точка входа для команды `clearmind-mcp`."""
    import anyio

    logger.info("Запуск ClearMind MCP сервера...")
    anyio.run(run_server)


if __name__ == "__main__":
    main()