"""
tests/test_analyzer_and_security.py

Тесты для compute_overload_score (agents/analyzer_agent.py) и для
детерминированных security-проверок (agents/security_policies.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from agents.analyzer_agent import compute_overload_score
from agents.security_policies import (
    check_file_size,
    check_no_pii_in_payload,
    check_outbound_call_allowed,
    check_persist_data_disabled,
    run_full_security_audit,
)
from mcp_server.models import AppSession, DataSource, NormalizedUsageData

BASE_DAY = datetime(2026, 6, 29)


def _light_usage() -> NormalizedUsageData:
    """Очень лёгкое, здоровое использование — низкий score ожидаем."""
    sessions = [
        AppSession(
            app_name="Notes", category="productivity",
            start_time=BASE_DAY.replace(hour=14),
            end_time=BASE_DAY.replace(hour=14, minute=20),
            duration_seconds=1200,
        )
    ]
    return NormalizedUsageData(
        source=DataSource.APPLE_SCREEN_TIME,
        period_start=BASE_DAY,
        period_end=BASE_DAY + timedelta(days=3),
        sessions=sessions,
        total_screen_time_seconds=1200,
        unique_apps_count=1,
    )


def _heavy_usage() -> NormalizedUsageData:
    """Тяжёлое использование с ночными сессиями и doomscrolling — высокий score."""
    sessions = []
    # Много doomscrolling сессий ночью
    for i in range(100):
        start = BASE_DAY.replace(hour=23, minute=0) + timedelta(minutes=i)
        sessions.append(
            AppSession(
                app_name="TikTok", category="social",
                start_time=start, end_time=start + timedelta(seconds=30),
                duration_seconds=30,
            )
        )
    return NormalizedUsageData(
        source=DataSource.TIKTOK_EXPORT,
        period_start=BASE_DAY,
        period_end=BASE_DAY + timedelta(days=1),
        sessions=sessions,
        total_screen_time_seconds=sum(s.duration_seconds for s in sessions),
        unique_apps_count=1,
    )


# ──────────────────────────────────────────────────────────────────
# compute_overload_score
# ──────────────────────────────────────────────────────────────────


def test_light_usage_gives_low_score():
    result = compute_overload_score(_light_usage())
    assert result.overload_score < 25
    assert result.severity_label == "низкая"


def test_heavy_usage_gives_high_score():
    result = compute_overload_score(_heavy_usage())
    assert result.overload_score >= 50
    assert result.severity_label in ("высокая", "критическая")


def test_overload_score_never_exceeds_100():
    result = compute_overload_score(_heavy_usage())
    assert 0 <= result.overload_score <= 100


def test_overload_score_is_reproducible():
    data = _heavy_usage()
    r1 = compute_overload_score(data)
    r2 = compute_overload_score(data)
    assert r1.overload_score == r2.overload_score
    assert r1.severity_label == r2.severity_label


def test_analysis_result_has_5_patterns():
    result = compute_overload_score(_light_usage())
    assert len(result.patterns) == 5


# ──────────────────────────────────────────────────────────────────
# security_policies
# ──────────────────────────────────────────────────────────────────


def test_check_file_size_within_limit(monkeypatch):
    monkeypatch.setenv("MAX_FILE_SIZE_BYTES", "1000")
    ok, _ = check_file_size(500)
    assert ok is True


def test_check_file_size_exceeds_limit(monkeypatch):
    monkeypatch.setenv("MAX_FILE_SIZE_BYTES", "1000")
    ok, msg = check_file_size(2000)
    assert ok is False
    assert "превышает лимит" in msg


def test_check_no_pii_clean_payload():
    ok, found = check_no_pii_in_payload({"overload_score": 80, "patterns": []})
    assert ok is True
    assert found == []


def test_check_no_pii_detects_blocked_field():
    ok, found = check_no_pii_in_payload({"user": {"email": "test@test.com", "score": 1}})
    assert ok is False
    assert "email" in found


def test_check_no_pii_recursive_detection_in_list():
    payload = {"items": [{"phone_number": "123"}, {"score": 5}]}
    ok, found = check_no_pii_in_payload(payload)
    assert ok is False
    assert "phone_number" in found


def test_check_outbound_call_allowed_gemini():
    ok, _ = check_outbound_call_allowed("generativelanguage.googleapis.com")
    assert ok is True


def test_check_outbound_call_blocked_unknown_domain():
    ok, msg = check_outbound_call_allowed("evil-tracker.example.com")
    assert ok is False
    assert "БЛОКИРОВАНО" in msg


def test_check_persist_data_disabled_default(monkeypatch):
    monkeypatch.setenv("PERSIST_USER_DATA", "false")
    ok, _ = check_persist_data_disabled()
    assert ok is True


def test_check_persist_data_flagged_when_true(monkeypatch):
    monkeypatch.setenv("PERSIST_USER_DATA", "true")
    ok, msg = check_persist_data_disabled()
    assert ok is False
    assert "ВНИМАНИЕ" in msg


def test_run_full_security_audit_all_pass(monkeypatch):
    monkeypatch.setenv("MAX_FILE_SIZE_BYTES", "10000")
    monkeypatch.setenv("PERSIST_USER_DATA", "false")
    result = run_full_security_audit(
        file_size_bytes=500,
        payload_sent_to_llm={"score": 80},
        outbound_domains_used=["generativelanguage.googleapis.com"],
    )
    assert result["all_passed"] is True


def test_run_full_security_audit_fails_on_pii(monkeypatch):
    monkeypatch.setenv("MAX_FILE_SIZE_BYTES", "10000")
    monkeypatch.setenv("PERSIST_USER_DATA", "false")
    result = run_full_security_audit(
        file_size_bytes=500,
        payload_sent_to_llm={"email": "leak@test.com"},
        outbound_domains_used=["generativelanguage.googleapis.com"],
    )
    assert result["all_passed"] is False
    assert result["checks"]["pii_check"]["passed"] is False