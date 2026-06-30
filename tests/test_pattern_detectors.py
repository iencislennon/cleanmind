"""
tests/test_pattern_detectors.py

Юнит-тесты для agents/pattern_detectors.py — самой важной детерминированной
логики проекта (от неё зависит воспроизводимость Overload Score).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from agents.analyzer_models import PatternSeverity
from agents.pattern_detectors import (
    ALL_DETECTORS,
    detect_app_switching,
    detect_doomscrolling,
    detect_night_usage,
    detect_peak_hours,
    detect_topic_diversity,
    top_apps_by_duration,
)
from mcp_server.models import AppSession, ContentTopic, DataSource, NormalizedUsageData

BASE_DAY = datetime(2026, 6, 29)


def _session(app: str, start_hour: int, start_minute: int, duration_seconds: int) -> AppSession:
    start = BASE_DAY.replace(hour=start_hour % 24, minute=start_minute)
    end = start + timedelta(seconds=duration_seconds)
    return AppSession(
        app_name=app, category="social", start_time=start, end_time=end,
        duration_seconds=duration_seconds,
    )


def _usage_data(sessions: list[AppSession], topics: list[ContentTopic] | None = None) -> NormalizedUsageData:
    return NormalizedUsageData(
        source=DataSource.APPLE_SCREEN_TIME,
        period_start=min(s.start_time for s in sessions),
        period_end=max(s.end_time for s in sessions) + timedelta(days=1),
        sessions=sessions,
        content_topics=topics or [],
        total_screen_time_seconds=sum(s.duration_seconds for s in sessions),
        unique_apps_count=len({s.app_name for s in sessions}),
    )


# ──────────────────────────────────────────────────────────────────
# Night usage
# ──────────────────────────────────────────────────────────────────


def test_detect_night_usage_low_when_no_night_sessions():
    data = _usage_data([_session("X", 14, 0, 3600)])
    pattern = detect_night_usage(data)
    assert pattern.severity == PatternSeverity.LOW
    assert pattern.raw_metric == 0


def test_detect_night_usage_critical_when_heavy_night_use():
    # 3 часа после полуночи -> явно critical (порог 2.0ч)
    sessions = [_session("X", 0, 0, 3 * 3600)]
    data = _usage_data(sessions)
    pattern = detect_night_usage(data)
    assert pattern.severity == PatternSeverity.CRITICAL
    assert pattern.score_contribution == 20.0  # max_points для этого паттерна


def test_detect_night_usage_is_session_classification_correct():
    s = _session("X", 23, 30, 60)
    assert s.is_night_session is True
    s2 = _session("X", 12, 0, 60)
    assert s2.is_night_session is False


# ──────────────────────────────────────────────────────────────────
# Doomscrolling
# ──────────────────────────────────────────────────────────────────


def test_detect_doomscrolling_low_with_few_short_sessions():
    sessions = [_session("X", 10, i, 60) for i in range(5)]
    data = _usage_data(sessions)
    pattern = detect_doomscrolling(data)
    assert pattern.severity == PatternSeverity.LOW


def test_detect_doomscrolling_critical_with_many_short_sessions():
    # period_days форсируем в 1 через ручную сборку
    sessions = [_session("TikTok", 10, i % 60, 30) for i in range(90)]
    data = NormalizedUsageData(
        source=DataSource.TIKTOK_EXPORT,
        period_start=BASE_DAY,
        period_end=BASE_DAY + timedelta(days=1),
        sessions=sessions,
        total_screen_time_seconds=sum(s.duration_seconds for s in sessions),
        unique_apps_count=1,
    )
    pattern = detect_doomscrolling(data)
    assert pattern.severity == PatternSeverity.CRITICAL


def test_detect_doomscrolling_long_sessions_not_counted():
    # Длинные сессии (>2 мин) НЕ должны считаться doomscrolling
    sessions = [_session("X", 10, 0, 600) for _ in range(50)]
    data = NormalizedUsageData(
        source=DataSource.APPLE_SCREEN_TIME,
        period_start=BASE_DAY,
        period_end=BASE_DAY + timedelta(days=1),
        sessions=sessions,
        total_screen_time_seconds=sum(s.duration_seconds for s in sessions),
        unique_apps_count=1,
    )
    pattern = detect_doomscrolling(data)
    assert pattern.raw_metric == 0


# ──────────────────────────────────────────────────────────────────
# App switching
# ──────────────────────────────────────────────────────────────────


def test_detect_app_switching_counts_fast_transitions():
    sessions = [
        _session("A", 10, 0, 60),
        _session("B", 10, 2, 60),  # начался через 60с после конца A -> switch
        _session("A", 10, 4, 60),
    ]
    data = NormalizedUsageData(
        source=DataSource.APPLE_SCREEN_TIME,
        period_start=BASE_DAY,
        period_end=BASE_DAY + timedelta(days=1),
        sessions=sessions,
        total_screen_time_seconds=180,
        unique_apps_count=2,
    )
    pattern = detect_app_switching(data)
    assert pattern.raw_metric == 2  # A->B, B->A


def test_detect_app_switching_ignores_same_app_transitions():
    sessions = [
        _session("A", 10, 0, 60),
        _session("A", 10, 2, 60),
    ]
    data = NormalizedUsageData(
        source=DataSource.APPLE_SCREEN_TIME,
        period_start=BASE_DAY,
        period_end=BASE_DAY + timedelta(days=1),
        sessions=sessions,
        total_screen_time_seconds=120,
        unique_apps_count=1,
    )
    pattern = detect_app_switching(data)
    assert pattern.raw_metric == 0


# ──────────────────────────────────────────────────────────────────
# Peak hours
# ──────────────────────────────────────────────────────────────────


def test_detect_peak_hours_finds_dominant_hour():
    sessions = [_session("X", 22, 0, 3600) for _ in range(5)] + [_session("X", 10, 0, 60)]
    data = _usage_data(sessions)
    pattern = detect_peak_hours(data)
    assert pattern.severity in (PatternSeverity.HIGH, PatternSeverity.CRITICAL)


# ──────────────────────────────────────────────────────────────────
# Topic diversity
# ──────────────────────────────────────────────────────────────────


def test_detect_topic_diversity_no_topics_returns_low():
    data = _usage_data([_session("X", 10, 0, 60)], topics=[])
    pattern = detect_topic_diversity(data)
    assert pattern.severity == PatternSeverity.LOW
    assert pattern.score_contribution == 0.0


def test_detect_topic_diversity_narrow_topic_is_high():
    topics = [ContentTopic(topic="doomscroll_news", timestamp=BASE_DAY) for _ in range(60)]
    data = _usage_data([_session("X", 10, 0, 60)], topics=topics)
    pattern = detect_topic_diversity(data)
    assert pattern.severity == PatternSeverity.HIGH


def test_detect_topic_diversity_diverse_topics_is_low():
    topics = [ContentTopic(topic=f"topic_{i}", timestamp=BASE_DAY) for i in range(60)]
    data = _usage_data([_session("X", 10, 0, 60)], topics=topics)
    pattern = detect_topic_diversity(data)
    assert pattern.severity == PatternSeverity.LOW


# ──────────────────────────────────────────────────────────────────
# Reproducibility — критичное свойство для итогового Overload Score
# ──────────────────────────────────────────────────────────────────


def test_all_detectors_are_deterministic():
    """Один и тот же вход должен ВСЕГДА давать один и тот же результат."""
    sessions = [_session("TikTok", h, 0, 90) for h in range(0, 24, 3)]
    data = _usage_data(sessions)

    first_run = [d(data).model_dump() for d in ALL_DETECTORS]
    second_run = [d(data).model_dump() for d in ALL_DETECTORS]

    assert first_run == second_run


def test_top_apps_by_duration_orders_correctly():
    sessions = [
        _session("A", 10, 0, 100),
        _session("B", 11, 0, 500),
        _session("A", 12, 0, 200),
    ]
    result = top_apps_by_duration(sessions, limit=2)
    assert result[0][0] == "B"  # больше всего времени
    assert result[1][0] == "A"