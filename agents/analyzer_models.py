"""
agents/analyzer_models.py

Модели данных для результатов анализа: отдельные паттерны перегрузки
и итоговый Overload Score. Вынесены в отдельный файл, чтобы и
Analyzer, и Coach, и FastAPI слой могли импортировать их без
циклических зависимостей.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PatternSeverity(str, Enum):
    """Насколько паттерн выражен — влияет на цвет/приоритет в UI и в плане Coach Agent."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class OverloadPattern(BaseModel):
    """Один обнаруженный паттерн информационной перегрузки."""

    pattern_id: str = Field(description="Машинное имя: peak_hours, topic_diversity и т.д.")
    title: str = Field(description="Человекочитаемое название для UI")
    severity: PatternSeverity
    score_contribution: float = Field(
        description="Сколько баллов из 100 этот паттерн добавляет в Overload Score"
    )
    explanation: str = Field(description="Объяснение на языке пользователя 16-25")
    raw_metric: float = Field(description="Сырое число метрики (часы, % и т.д.)")
    raw_metric_unit: str = Field(description="Единица измерения: hours, percent, count")


class AnalysisResult(BaseModel):
    """Итоговый результат работы Analyzer Agent — то, что уходит в Coach Agent."""

    overload_score: int = Field(ge=0, le=100, description="Итоговый Overload Score 0-100")
    severity_label: str = Field(description="низкая / умеренная / высокая / критическая")
    patterns: list[OverloadPattern] = Field(default_factory=list)
    total_screen_time_hours: float
    period_days: int
    top_apps: list[tuple[str, float]] = Field(
        default_factory=list, description="Топ-5 приложений и часы на них"
    )
    summary_for_coach: str = Field(
        description="Краткое резюме для Coach Agent — контекст для начала диалога"
    )