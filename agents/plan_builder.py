"""
agents/plan_builder.py

Чистая логика построения детокс-плана из обнаруженных паттернов.
Сопоставляет каждый значимый паттерн (severity >= MODERATE) с конкретными,
измеримыми шагами — библиотека шагов ниже, без участия LLM на этом уровне.

LLM (внутри Coach Agent) используется чтобы ПЕРСОНАЛИЗИРОВАТЬ формулировки
под user_context (учёба/работа/скука), но сама структура и набор кандидатов
шагов — детерминированы, чтобы план был осмысленным и не "плыл" между
сессиями с одним и тем же score.
"""

from __future__ import annotations

import uuid

from agents.analyzer_models import AnalysisResult, OverloadPattern, PatternSeverity
from agents.coach_models import DetoxPlan, DetoxStep

# Библиотека шагов по pattern_id. Каждому паттерну сопоставлено 1-2 шага,
# которые имеет смысл предложить если паттерн выражен (MODERATE и выше).
STEP_LIBRARY: dict[str, list[dict]] = {
    "night_usage": [
        {
            "title": "Цифровой комендантский час",
            "description": (
                "Телефон уходит в другую комнату (или в режим 'Не беспокоить' "
                "без возможности уведомлений) за 30 минут до привычного времени сна."
            ),
            "measurable_target": "0 минут экранного времени после 23:00",
        }
    ],
    "doomscrolling": [
        {
            "title": "Правило 'одна причина'",
            "description": (
                "Перед тем как открыть приложение — назвать себе одну конкретную "
                "причину (не 'просто посмотреть'). Если причины нет — не открывать."
            ),
            "measurable_target": "Сократить короткие сессии (<2 мин) на 50%",
        }
    ],
    "app_switching": [
        {
            "title": "Блоки фокуса 25/5",
            "description": (
                "25 минут с уведомлениями выключенными на всех приложениях из топ-3 "
                "по времени, затем 5 минут свободного использования."
            ),
            "measurable_target": "Минимум 3 блока фокуса в день",
        }
    ],
    "peak_hours": [
        {
            "title": "Замена пикового часа",
            "description": (
                "В тот час, когда обычно больше всего сидишь в телефоне — "
                "заранее запланировать что-то офлайн (даже 15-минутную прогулку)."
            ),
            "measurable_target": "Заменить пиковый час офлайн-активностью 4 из 7 дней",
        }
    ],
    "topic_diversity": [
        {
            "title": "Сознательное разнообразие ленты",
            "description": (
                "Один раз в день специально посмотреть контент вне обычной темы — "
                "это сбивает алгоритмическую петлю rabbit hole."
            ),
            "measurable_target": "Минимум 1 новая тема контента в день",
        }
    ],
}


def _significant_patterns(patterns: list[OverloadPattern]) -> list[OverloadPattern]:
    """Отбирает только те паттерны, по которым реально стоит давать шаги."""
    significant = {PatternSeverity.MODERATE, PatternSeverity.HIGH, PatternSeverity.CRITICAL}
    return [p for p in patterns if p.severity in significant]


def build_detox_plan(analysis: AnalysisResult, user_context: str = "") -> DetoxPlan:
    """
    Строит DetoxPlan на основе результатов анализа.

    Распределяет шаги по 7 дням: в день 1 — самые простые/безопасные,
    к концу недели — более требовательные. Берём не более 5 шагов суммарно,
    чтобы план не выглядел подавляюще (это сам по себе anti-overload принцип).
    """
    significant = _significant_patterns(analysis.patterns)
    # Сортируем по вкладу в score — сначала решаем то, что бьёт сильнее всего
    significant.sort(key=lambda p: p.score_contribution, reverse=True)

    steps: list[DetoxStep] = []
    day_cursor = 1

    for pattern in significant[:5]:  # не больше 5 шагов в плане
        candidates = STEP_LIBRARY.get(pattern.pattern_id, [])
        if not candidates:
            continue
        template = candidates[0]
        steps.append(
            DetoxStep(
                step_id=str(uuid.uuid4())[:8],
                day=day_cursor,
                title=template["title"],
                description=template["description"],
                related_pattern_id=pattern.pattern_id,
                measurable_target=template["measurable_target"],
            )
        )
        day_cursor = min(7, day_cursor + 1)

    return DetoxPlan(
        plan_id=str(uuid.uuid4())[:8],
        overload_score_at_creation=analysis.overload_score,
        steps=steps,
        user_context=user_context,
    )