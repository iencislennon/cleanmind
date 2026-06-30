"""
mcp_server/parsers.py

Парсеры для четырёх форматов экспорта данных.
Каждый парсер — чистая функция: bytes -> ParseResult.
Никакого I/O кроме чтения переданных байтов — это важно для Guard Agent,
который должен гарантировать что файл не пишется на диск и не уходит наружу.
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from datetime import datetime

from mcp_server.models import (
    AppSession,
    ContentTopic,
    DataSource,
    NormalizedUsageData,
    ParseResult,
)

# Категории приложений — используется чтобы Analyzer Agent понимал
# что "TikTok" и "Instagram" это social, а не два разных типа.
APP_CATEGORY_MAP: dict[str, str] = {
    "tiktok": "social",
    "instagram": "social",
    "youtube": "entertainment",
    "telegram": "messaging",
    "whatsapp": "messaging",
    "twitter": "social",
    "x": "social",
    "netflix": "entertainment",
    "news": "news",
    "chrome": "browser",
    "safari": "browser",
}


def _categorize(app_name: str) -> str:
    """Грубая категоризация по имени приложения. В реальном проекте — справочник пошире."""
    lowered = app_name.lower()
    for key, category in APP_CATEGORY_MAP.items():
        if key in lowered:
            return category
    return "other"


# ──────────────────────────────────────────────────────────────────
# 1. Apple Screen Time (XML)
# ──────────────────────────────────────────────────────────────────


def parse_apple_screen_time(raw_bytes: bytes) -> ParseResult:
    """
    Парсит экспорт Apple Screen Time.

    Реальный формат Apple — это закрытая база (knowledgeC.db), но пользователи
    обычно экспортируют через сторонние shortcuts в XML вида:

    <ScreenTimeExport>
      <App name="TikTok" category="Social">
        <Session start="2026-06-29T22:15:00" end="2026-06-29T23:40:00"/>
      </App>
    </ScreenTimeExport>
    """
    warnings: list[str] = []
    try:
        root = ET.fromstring(raw_bytes)
    except ET.ParseError as exc:
        return ParseResult(success=False, error_message=f"Невалидный XML: {exc}")

    sessions: list[AppSession] = []
    apps_seen: set[str] = set()

    for app_el in root.findall("App"):
        app_name = app_el.get("name", "Unknown")
        category = app_el.get("category") or _categorize(app_name)
        apps_seen.add(app_name)

        for session_el in app_el.findall("Session"):
            start_raw = session_el.get("start")
            end_raw = session_el.get("end")
            if not start_raw or not end_raw:
                warnings.append(f"Пропущена сессия без start/end в {app_name}")
                continue
            try:
                start = datetime.fromisoformat(start_raw)
                end = datetime.fromisoformat(end_raw)
            except ValueError:
                warnings.append(f"Невалидный формат даты в {app_name}: {start_raw} / {end_raw}")
                continue

            duration = max(0, int((end - start).total_seconds()))
            sessions.append(
                AppSession(
                    app_name=app_name,
                    category=category,
                    start_time=start,
                    end_time=end,
                    duration_seconds=duration,
                )
            )

    if not sessions:
        return ParseResult(
            success=False,
            error_message="Не найдено ни одной валидной сессии в файле",
            warnings=warnings,
        )

    period_start = min(s.start_time for s in sessions)
    period_end = max(s.end_time for s in sessions)
    total_seconds = sum(s.duration_seconds for s in sessions)

    data = NormalizedUsageData(
        source=DataSource.APPLE_SCREEN_TIME,
        period_start=period_start,
        period_end=period_end,
        sessions=sessions,
        total_screen_time_seconds=total_seconds,
        unique_apps_count=len(apps_seen),
    )

    return ParseResult(success=True, data=data, rows_parsed=len(sessions), warnings=warnings)


# ──────────────────────────────────────────────────────────────────
# 2. Google Digital Wellbeing (CSV)
# ──────────────────────────────────────────────────────────────────


def parse_digital_wellbeing(raw_bytes: bytes) -> ParseResult:
    """
    Парсит экспорт Google Digital Wellbeing.

    Ожидаемый формат CSV (Android экспортирует похожим образом через
    Takeout): app_name,start_time,end_time,category
    """
    warnings: list[str] = []
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ParseResult(success=False, error_message=f"Ошибка кодировки: {exc}")

    reader = csv.DictReader(io.StringIO(text))
    required_cols = {"app_name", "start_time", "end_time"}
    if reader.fieldnames is None or not required_cols.issubset(set(reader.fieldnames)):
        return ParseResult(
            success=False,
            error_message=f"CSV должен содержать колонки: {required_cols}",
        )

    sessions: list[AppSession] = []
    apps_seen: set[str] = set()

    for i, row in enumerate(reader, start=1):
        app_name = row.get("app_name", "").strip()
        if not app_name:
            warnings.append(f"Строка {i}: пустое имя приложения, пропущена")
            continue
        apps_seen.add(app_name)

        try:
            start = datetime.fromisoformat(row["start_time"])
            end = datetime.fromisoformat(row["end_time"])
        except (ValueError, KeyError):
            warnings.append(f"Строка {i}: невалидная дата, пропущена")
            continue

        category = row.get("category") or _categorize(app_name)
        duration = max(0, int((end - start).total_seconds()))

        sessions.append(
            AppSession(
                app_name=app_name,
                category=category,
                start_time=start,
                end_time=end,
                duration_seconds=duration,
            )
        )

    if not sessions:
        return ParseResult(
            success=False,
            error_message="Не найдено ни одной валидной строки",
            warnings=warnings,
        )

    period_start = min(s.start_time for s in sessions)
    period_end = max(s.end_time for s in sessions)
    total_seconds = sum(s.duration_seconds for s in sessions)

    data = NormalizedUsageData(
        source=DataSource.GOOGLE_DIGITAL_WELLBEING,
        period_start=period_start,
        period_end=period_end,
        sessions=sessions,
        total_screen_time_seconds=total_seconds,
        unique_apps_count=len(apps_seen),
    )

    return ParseResult(success=True, data=data, rows_parsed=len(sessions), warnings=warnings)


# ──────────────────────────────────────────────────────────────────
# 3 & 4. TikTok / Instagram Data Export (JSON)
# ──────────────────────────────────────────────────────────────────


def _parse_social_export(raw_bytes: bytes, source: DataSource) -> ParseResult:
    """
    Общая логика для TikTok и Instagram — оба отдают похожий JSON формат
    при официальном запросе "Скачать мои данные".

    Ожидаемая структура (упрощённая под наши нужды):
    {
      "video_browsing_history": [
        {"video_topic": "...", "watch_time": "2026-06-29T22:15:00", "duration_seconds": 45}
      ]
    }
    """
    warnings: list[str] = []
    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        return ParseResult(success=False, error_message=f"Невалидный JSON: {exc}")

    history = payload.get("video_browsing_history", [])
    if not isinstance(history, list):
        return ParseResult(
            success=False,
            error_message="Поле video_browsing_history отсутствует или некорректно",
        )

    topics: list[ContentTopic] = []
    sessions: list[AppSession] = []
    app_name = "TikTok" if source == DataSource.TIKTOK_EXPORT else "Instagram"

    for i, entry in enumerate(history, start=1):
        topic_name = entry.get("video_topic", "unknown")
        watch_time_raw = entry.get("watch_time")
        duration = entry.get("duration_seconds", 0)

        if not watch_time_raw:
            warnings.append(f"Запись {i}: нет времени просмотра, пропущена")
            continue

        try:
            watch_time = datetime.fromisoformat(watch_time_raw)
        except ValueError:
            warnings.append(f"Запись {i}: невалидная дата {watch_time_raw}")
            continue

        topics.append(ContentTopic(topic=topic_name, timestamp=watch_time))

        # Каждый просмотр трактуем как микро-сессию — нужно для расчёта
        # "бесконечной прокрутки" (много коротких сессий подряд)
        sessions.append(
            AppSession(
                app_name=app_name,
                category="social",
                start_time=watch_time,
                end_time=watch_time,
                duration_seconds=int(duration),
            )
        )

    if not sessions:
        return ParseResult(
            success=False,
            error_message="Не найдено записей о просмотрах",
            warnings=warnings,
        )

    period_start = min(s.start_time for s in sessions)
    period_end = max(s.end_time for s in sessions)
    total_seconds = sum(s.duration_seconds for s in sessions)

    data = NormalizedUsageData(
        source=source,
        period_start=period_start,
        period_end=period_end,
        sessions=sessions,
        content_topics=topics,
        total_screen_time_seconds=total_seconds,
        unique_apps_count=1,
    )

    return ParseResult(success=True, data=data, rows_parsed=len(sessions), warnings=warnings)


def parse_tiktok_export(raw_bytes: bytes) -> ParseResult:
    return _parse_social_export(raw_bytes, DataSource.TIKTOK_EXPORT)


def parse_instagram_export(raw_bytes: bytes) -> ParseResult:
    return _parse_social_export(raw_bytes, DataSource.INSTAGRAM_EXPORT)


# ──────────────────────────────────────────────────────────────────
# Реестр парсеров — единая точка входа для MCP сервера
# ──────────────────────────────────────────────────────────────────

PARSERS = {
    DataSource.APPLE_SCREEN_TIME: parse_apple_screen_time,
    DataSource.GOOGLE_DIGITAL_WELLBEING: parse_digital_wellbeing,
    DataSource.TIKTOK_EXPORT: parse_tiktok_export,
    DataSource.INSTAGRAM_EXPORT: parse_instagram_export,
}


def parse(source: DataSource, raw_bytes: bytes) -> ParseResult:
    """Главная точка входа: выбирает нужный парсер по источнику данных."""
    parser_fn = PARSERS.get(source)
    if parser_fn is None:
        return ParseResult(success=False, error_message=f"Неизвестный источник: {source}")
    return parser_fn(raw_bytes)