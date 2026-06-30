"""
mcp_server/models.py

Pydantic-модели для нормализованных данных об использовании устройства.
Все парсеры (Screen Time, Digital Wellbeing, TikTok, Instagram) приводят
свои форматы к ЭТИМ единым моделям — это позволяет Analyzer Agent работать
с одной структурой данных независимо от источника.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    """Откуда пришли данные — нужно для UI и для аудита Guard Agent."""

    APPLE_SCREEN_TIME = "apple_screen_time"
    GOOGLE_DIGITAL_WELLBEING = "google_digital_wellbeing"
    TIKTOK_EXPORT = "tiktok_export"
    INSTAGRAM_EXPORT = "instagram_export"


class AppSession(BaseModel):
    """Одна сессия использования одного приложения."""

    app_name: str
    category: str | None = Field(
        default=None,
        description="Категория приложения: social, news, entertainment, productivity и т.д.",
    )
    start_time: datetime
    end_time: datetime
    duration_seconds: int

    @property
    def hour_of_day(self) -> int:
        """Час суток когда началась сессия — нужен для анализа ночного использования."""
        return self.start_time.hour

    @property
    def is_night_session(self) -> bool:
        """Сессия после 23:00 или до 5:00 — паттерн перегрузки."""
        return self.hour_of_day >= 23 or self.hour_of_day < 5


class ContentTopic(BaseModel):
    """Тема контента, который пролистал пользователь (из TikTok/Instagram export)."""

    topic: str
    count: int = 1
    timestamp: datetime | None = None


class NormalizedUsageData(BaseModel):
    """
    Единая структура данных после парсинга ЛЮБОГО источника.

    Это контракт между Parser Agent и Analyzer Agent — Analyzer
    никогда не видит сырые XML/CSV/JSON, только эту модель.
    """

    source: DataSource
    period_start: datetime
    period_end: datetime
    sessions: list[AppSession] = Field(default_factory=list)
    content_topics: list[ContentTopic] = Field(default_factory=list)

    # Агрегаты — считаются один раз при парсинге, чтобы не пересчитывать в анализаторе
    total_screen_time_seconds: int = 0
    unique_apps_count: int = 0

    class Config:
        json_schema_extra = {
            "example": {
                "source": "apple_screen_time",
                "period_start": "2026-06-23T00:00:00",
                "period_end": "2026-06-30T00:00:00",
                "sessions": [],
                "content_topics": [],
                "total_screen_time_seconds": 32400,
                "unique_apps_count": 12,
            }
        }


class ParseResult(BaseModel):
    """Результат работы парсера — данные + метаданные о самом процессе парсинга."""

    success: bool
    data: NormalizedUsageData | None = None
    error_message: str | None = None
    rows_parsed: int = 0
    warnings: list[str] = Field(default_factory=list)