"""
agents/pattern_detectors.py

Чистые функции, которые вычисляют 5 паттернов информационной перегрузки
из NormalizedUsageData. Каждая функция возвращает OverloadPattern или None
(если паттерн не обнаружен / не выражен).

Вынесены отдельно от analyzer_agent.py намеренно: это детерминированная
математика, не LLM-логика. LLM (внутри Analyzer Agent) используется только
чтобы собрать summary_for_coach человеческим языком — сами цифры считаются
здесь, без участия модели, чтобы Overload Score был воспроизводим и не
"галлюцинировал".
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from agents.analyzer_models import OverloadPattern, PatternSeverity
from mcp_server.models import AppSession, NormalizedUsageData

# ──────────────────────────────────────────────────────────────────
# Пороговые значения — вынесены в константы, чтобы их было легко
# подкрутить во время демо/тестирования без переписывания логики
# ──────────────────────────────────────────────────────────────────

NIGHT_HOURS_WARNING_THRESHOLD = 0.5  # часов в среднем за ночь
NIGHT_HOURS_CRITICAL_THRESHOLD = 2.0

SHORT_SESSION_SECONDS = 120  # сессия короче 2 минут считается "скроллом"
DOOMSCROLL_SESSION_COUNT_WARNING = 30  # короткие сессии в день
DOOMSCROLL_SESSION_COUNT_CRITICAL = 80

SWITCH_GAP_SECONDS = 120  # переключение между приложениями быстрее этого = "switching"
SWITCH_COUNT_WARNING = 40
SWITCH_COUNT_CRITICAL = 100

PEAK_HOUR_SHARE_WARNING = 0.35  # доля всего времени в самый загруженный час
PEAK_HOUR_SHARE_CRITICAL = 0.55


def _severity_from_thresholds(
    value: float, warning: float, critical: float
) -> PatternSeverity:
    """Общая логика перевода сырого числа в категорию серьёзности."""
    if value >= critical:
        return PatternSeverity.CRITICAL
    if value >= warning:
        return PatternSeverity.HIGH if value >= (warning + critical) / 2 else PatternSeverity.MODERATE
    return PatternSeverity.LOW


def _score_from_severity(severity: PatternSeverity, max_points: float) -> float:
    """Конвертирует severity в баллы вклада в общий Overload Score (макс max_points)."""
    weights = {
        PatternSeverity.LOW: 0.1,
        PatternSeverity.MODERATE: 0.4,
        PatternSeverity.HIGH: 0.7,
        PatternSeverity.CRITICAL: 1.0,
    }
    return round(max_points * weights[severity], 1)


# ──────────────────────────────────────────────────────────────────
# Паттерн 1: Ночное потребление
# ──────────────────────────────────────────────────────────────────


def detect_night_usage(data: NormalizedUsageData) -> OverloadPattern:
    night_seconds = sum(s.duration_seconds for s in data.sessions if s.is_night_session)
    period_days = max(1, (data.period_end - data.period_start).days)
    avg_night_hours_per_day = (night_seconds / 3600) / period_days

    severity = _severity_from_thresholds(
        avg_night_hours_per_day, NIGHT_HOURS_WARNING_THRESHOLD, NIGHT_HOURS_CRITICAL_THRESHOLD
    )

    return OverloadPattern(
        pattern_id="night_usage",
        title="Ночное использование",
        severity=severity,
        score_contribution=_score_from_severity(severity, max_points=20),
        explanation=(
            f"В среднем {avg_night_hours_per_day:.1f} ч/ночь в телефоне после 23:00. "
            "Это напрямую бьёт по качеству сна и способности концентрироваться на следующий день."
        ),
        raw_metric=round(avg_night_hours_per_day, 2),
        raw_metric_unit="hours_per_night",
    )


# ──────────────────────────────────────────────────────────────────
# Паттерн 2: Doomscrolling (много очень коротких сессий)
# ──────────────────────────────────────────────────────────────────


def detect_doomscrolling(data: NormalizedUsageData) -> OverloadPattern:
    short_sessions = [s for s in data.sessions if s.duration_seconds <= SHORT_SESSION_SECONDS]
    period_days = max(1, (data.period_end - data.period_start).days)
    avg_short_sessions_per_day = len(short_sessions) / period_days

    severity = _severity_from_thresholds(
        avg_short_sessions_per_day,
        DOOMSCROLL_SESSION_COUNT_WARNING,
        DOOMSCROLL_SESSION_COUNT_CRITICAL,
    )

    return OverloadPattern(
        pattern_id="doomscrolling",
        title="Бесконечная прокрутка",
        severity=severity,
        score_contribution=_score_from_severity(severity, max_points=25),
        explanation=(
            f"{avg_short_sessions_per_day:.0f} коротких заходов в день (<2 мин каждый) — "
            "классический паттерн compulsive checking без цели."
        ),
        raw_metric=round(avg_short_sessions_per_day, 1),
        raw_metric_unit="sessions_per_day",
    )


# ──────────────────────────────────────────────────────────────────
# Паттерн 3: Switching frequency (частое переключение между приложениями)
# ──────────────────────────────────────────────────────────────────


def detect_app_switching(data: NormalizedUsageData) -> OverloadPattern:
    sorted_sessions = sorted(data.sessions, key=lambda s: s.start_time)
    switches = 0

    for prev, curr in zip(sorted_sessions, sorted_sessions[1:]):
        gap = (curr.start_time - prev.end_time).total_seconds()
        if prev.app_name != curr.app_name and 0 <= gap <= SWITCH_GAP_SECONDS:
            switches += 1

    period_days = max(1, (data.period_end - data.period_start).days)
    avg_switches_per_day = switches / period_days

    severity = _severity_from_thresholds(
        avg_switches_per_day, SWITCH_COUNT_WARNING, SWITCH_COUNT_CRITICAL
    )

    return OverloadPattern(
        pattern_id="app_switching",
        title="Частое переключение между приложениями",
        severity=severity,
        score_contribution=_score_from_severity(severity, max_points=20),
        explanation=(
            f"{avg_switches_per_day:.0f} переключений в день между приложениями за <2 мин. "
            "Мозг не успевает фокусироваться — это и есть субъективное ощущение "
            "'всё срочно, ничего не успеваю'."
        ),
        raw_metric=round(avg_switches_per_day, 1),
        raw_metric_unit="switches_per_day",
    )


# ──────────────────────────────────────────────────────────────────
# Паттерн 4: Пиковые часы (концентрация потребления в один час)
# ──────────────────────────────────────────────────────────────────


def detect_peak_hours(data: NormalizedUsageData) -> OverloadPattern:
    by_hour: Counter[int] = Counter()
    for s in data.sessions:
        by_hour[s.hour_of_day] += s.duration_seconds

    total = sum(by_hour.values()) or 1
    peak_hour, peak_seconds = by_hour.most_common(1)[0] if by_hour else (0, 0)
    peak_share = peak_seconds / total

    severity = _severity_from_thresholds(
        peak_share, PEAK_HOUR_SHARE_WARNING, PEAK_HOUR_SHARE_CRITICAL
    )

    return OverloadPattern(
        pattern_id="peak_hours",
        title="Концентрация в пиковые часы",
        severity=severity,
        score_contribution=_score_from_severity(severity, max_points=15),
        explanation=(
            f"{peak_share * 100:.0f}% всего экранного времени приходится на {peak_hour}:00–"
            f"{(peak_hour + 1) % 24}:00. Один час перегружен сильнее остальных — "
            "стоит понять что в это время триггерит использование."
        ),
        raw_metric=round(peak_share * 100, 1),
        raw_metric_unit="percent",
    )


# ──────────────────────────────────────────────────────────────────
# Паттерн 5: Topic diversity (разнообразие тем контента)
# ──────────────────────────────────────────────────────────────────


def detect_topic_diversity(data: NormalizedUsageData) -> OverloadPattern:
    if not data.content_topics:
        # Нет данных о темах (например, источник Screen Time без content_topics) —
        # паттерн не применим, возвращаем LOW с пояснением
        return OverloadPattern(
            pattern_id="topic_diversity",
            title="Разнообразие тем контента",
            severity=PatternSeverity.LOW,
            score_contribution=0.0,
            explanation="Источник данных не содержит информации о темах контента.",
            raw_metric=0.0,
            raw_metric_unit="unique_topics",
        )

    topic_counts = Counter(t.topic for t in data.content_topics)
    unique_topics = len(topic_counts)
    total_views = sum(topic_counts.values())

    # Низкое разнообразие (мало уникальных тем при многих просмотрах) —
    # признак "застревания" в одном типе контента (например, doom-новости)
    diversity_ratio = unique_topics / max(1, total_views)
    is_narrow = diversity_ratio < 0.05 and total_views > 50

    severity = PatternSeverity.HIGH if is_narrow else PatternSeverity.LOW
    top_topic, top_count = topic_counts.most_common(1)[0]
    dominance = top_count / total_views

    return OverloadPattern(
        pattern_id="topic_diversity",
        title="Разнообразие тем контента",
        severity=severity,
        score_contribution=_score_from_severity(severity, max_points=20),
        explanation=(
            f"Тема «{top_topic}» занимает {dominance * 100:.0f}% всех просмотров "
            f"({unique_topics} уникальных тем всего). Сильный перекос в одну тему "
            "часто усиливает тревожность через algorithmic rabbit hole."
        ),
        raw_metric=unique_topics,
        raw_metric_unit="unique_topics",
    )


# ──────────────────────────────────────────────────────────────────
# Реестр всех детекторов
# ──────────────────────────────────────────────────────────────────

ALL_DETECTORS = [
    detect_night_usage,
    detect_doomscrolling,
    detect_app_switching,
    detect_peak_hours,
    detect_topic_diversity,
]


def top_apps_by_duration(sessions: list[AppSession], limit: int = 5) -> list[tuple[str, float]]:
    """Возвращает топ-N приложений по суммарному времени (в часах)."""
    totals: Counter[str] = Counter()
    for s in sessions:
        totals[s.app_name] += s.duration_seconds

    return [(app, round(seconds / 3600, 1)) for app, seconds in totals.most_common(limit)]