"""
tests/test_parsers.py

Юнит-тесты для mcp_server/parsers.py. Покрывают happy path и основные
edge cases для каждого из четырёх форматов экспорта.
"""

from __future__ import annotations

import json

from mcp_server.models import DataSource
from mcp_server.parsers import (
    parse_apple_screen_time,
    parse_digital_wellbeing,
    parse_instagram_export,
    parse_tiktok_export,
)


# ──────────────────────────────────────────────────────────────────
# Apple Screen Time (XML)
# ──────────────────────────────────────────────────────────────────


def test_parse_apple_screen_time_happy_path():
    xml = b"""<?xml version="1.0"?>
    <ScreenTimeExport>
      <App name="TikTok" category="Social">
        <Session start="2026-06-29T22:15:00" end="2026-06-29T23:40:00"/>
        <Session start="2026-06-30T08:00:00" end="2026-06-30T08:05:00"/>
      </App>
      <App name="Safari" category="Browser">
        <Session start="2026-06-29T10:00:00" end="2026-06-29T10:30:00"/>
      </App>
    </ScreenTimeExport>"""

    result = parse_apple_screen_time(xml)

    assert result.success is True
    assert result.data is not None
    assert result.data.source == DataSource.APPLE_SCREEN_TIME
    assert result.data.unique_apps_count == 2
    assert len(result.data.sessions) == 3
    # 85 + 5 + 30 минут = 7200 секунд
    assert result.data.total_screen_time_seconds == 85 * 60 + 5 * 60 + 30 * 60


def test_parse_apple_screen_time_invalid_xml():
    result = parse_apple_screen_time(b"not xml at all <<<")
    assert result.success is False
    assert "Невалидный XML" in result.error_message


def test_parse_apple_screen_time_empty_sessions():
    xml = b'<ScreenTimeExport><App name="Empty"></App></ScreenTimeExport>'
    result = parse_apple_screen_time(xml)
    assert result.success is False
    assert "Не найдено" in result.error_message


def test_parse_apple_screen_time_skips_malformed_session():
    xml = b"""<ScreenTimeExport>
      <App name="X">
        <Session start="not-a-date" end="2026-06-29T23:40:00"/>
        <Session start="2026-06-29T22:15:00" end="2026-06-29T23:40:00"/>
      </App>
    </ScreenTimeExport>"""
    result = parse_apple_screen_time(xml)
    assert result.success is True
    assert len(result.data.sessions) == 1
    assert len(result.warnings) == 1


# ──────────────────────────────────────────────────────────────────
# Google Digital Wellbeing (CSV)
# ──────────────────────────────────────────────────────────────────


def test_parse_digital_wellbeing_happy_path():
    csv_content = (
        "app_name,start_time,end_time,category\n"
        "YouTube,2026-06-29T20:00:00,2026-06-29T21:15:00,entertainment\n"
        "Telegram,2026-06-29T21:20:00,2026-06-29T21:25:00,messaging\n"
    ).encode("utf-8")

    result = parse_digital_wellbeing(csv_content)

    assert result.success is True
    assert result.data.unique_apps_count == 2
    assert result.rows_parsed == 2


def test_parse_digital_wellbeing_missing_columns():
    csv_content = b"wrong_column,another\nval1,val2\n"
    result = parse_digital_wellbeing(csv_content)
    assert result.success is False
    assert "колонки" in result.error_message


def test_parse_digital_wellbeing_auto_categorizes_when_missing():
    csv_content = (
        "app_name,start_time,end_time\n"
        "TikTok,2026-06-29T20:00:00,2026-06-29T20:10:00\n"
    ).encode("utf-8")
    result = parse_digital_wellbeing(csv_content)
    assert result.success is True
    assert result.data.sessions[0].category == "social"


# ──────────────────────────────────────────────────────────────────
# TikTok / Instagram (JSON)
# ──────────────────────────────────────────────────────────────────


def _build_social_export(num_entries: int = 3) -> bytes:
    history = [
        {
            "video_topic": f"topic_{i % 2}",
            "watch_time": f"2026-06-29T2{i % 4}:00:00",
            "duration_seconds": 30 + i,
        }
        for i in range(num_entries)
    ]
    return json.dumps({"video_browsing_history": history}).encode("utf-8")


def test_parse_tiktok_export_happy_path():
    raw = _build_social_export(5)
    result = parse_tiktok_export(raw)

    assert result.success is True
    assert result.data.source == DataSource.TIKTOK_EXPORT
    assert len(result.data.sessions) == 5
    assert len(result.data.content_topics) == 5


def test_parse_instagram_export_happy_path():
    raw = _build_social_export(2)
    result = parse_instagram_export(raw)
    assert result.success is True
    assert result.data.source == DataSource.INSTAGRAM_EXPORT


def test_parse_social_export_invalid_json():
    result = parse_tiktok_export(b"{not valid json")
    assert result.success is False
    assert "Невалидный JSON" in result.error_message


def test_parse_social_export_missing_history_field():
    raw = json.dumps({"something_else": []}).encode("utf-8")
    result = parse_tiktok_export(raw)
    assert result.success is False