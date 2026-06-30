"""
agents/analyzer_agent.py

Analyzer Agent — ОРКЕСТРАТОР системы ClearMind.

Роль: получает NormalizedUsageData от Parser Agent (через A2A), прогоняет
все 5 детекторов паттернов (детерминированная математика, см.
pattern_detectors.py), считает итоговый Overload Score, и — это единственное
место где используется LLM в этом агенте — просит Gemini сформулировать
человекочитаемое summary_for_coach, которое передаётся дальше Coach Agent'у.

Этот агент называется "оркестратором" не просто из-за бизнес-роли, а
архитектурно: именно он инициирует вызовы Parser Agent и Coach Agent через
A2A протокол (см. a2a/protocol.py), то есть управляет последовательностью
работы всей мультиагентной системы.
"""

from __future__ import annotations

import logging
import os

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from agents.analyzer_models import AnalysisResult
from agents.pattern_detectors import ALL_DETECTORS, top_apps_by_duration
from mcp_server.models import NormalizedUsageData

logger = logging.getLogger("clearmind.analyzer_agent")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


# ──────────────────────────────────────────────────────────────────
# Чистая функция расчёта — НЕ зависит от LLM, полностью детерминирована
# ──────────────────────────────────────────────────────────────────


def compute_overload_score(data: NormalizedUsageData) -> AnalysisResult:
    """
    Прогоняет все детекторы и считает итоговый Overload Score (0-100).

    Это намеренно вызывается как обычная Python-функция, а не как LLM tool,
    чтобы число было ВОСПРОИЗВОДИМО: одни и те же данные всегда дают один
    и тот же score. LLM подключается уже после, только для текстового слоя.
    """
    patterns = [detector(data) for detector in ALL_DETECTORS]

    # Сумма вкладов, ограниченная сверху 100
    raw_score = sum(p.score_contribution for p in patterns)
    overload_score = min(100, round(raw_score))

    if overload_score >= 75:
        severity_label = "критическая"
    elif overload_score >= 50:
        severity_label = "высокая"
    elif overload_score >= 25:
        severity_label = "умеренная"
    else:
        severity_label = "низкая"

    period_days = max(1, (data.period_end - data.period_start).days)

    return AnalysisResult(
        overload_score=overload_score,
        severity_label=severity_label,
        patterns=patterns,
        total_screen_time_hours=round(data.total_screen_time_seconds / 3600, 1),
        period_days=period_days,
        top_apps=top_apps_by_duration(data.sessions),
        # summary_for_coach заполняется отдельно через LLM-вызов ниже,
        # здесь временная заглушка на случай если LLM-шаг пропущен
        summary_for_coach=_fallback_summary(overload_score, severity_label, patterns),
    )


def _fallback_summary(overload_score: int, severity_label: str, patterns: list) -> str:
    """Резервное summary без LLM — на случай сбоя или для unit-тестов."""
    top_pattern = max(patterns, key=lambda p: p.score_contribution, default=None)
    top_part = f" Сильнее всего выражен паттерн: {top_pattern.title}." if top_pattern else ""
    return f"Overload Score {overload_score}/100 ({severity_label}).{top_part}"


# ──────────────────────────────────────────────────────────────────
# ADK Tool-обёртка — то, что LLM-агент реально вызывает
# ──────────────────────────────────────────────────────────────────


def analyze_usage_tool(usage_data_json: str) -> str:
    """
    ADK Tool: принимает JSON-строку NormalizedUsageData, возвращает
    JSON-строку AnalysisResult.

    Названо как tool (а не как внутренний метод) специально — это то,
    что объявлено в Gemini function-calling схеме агента и то, что
    видно в логах вызовов при демонстрации на видео.
    """
    data = NormalizedUsageData.model_validate_json(usage_data_json)
    result = compute_overload_score(data)
    logger.info(
        "Analyzer: score=%d severity=%s patterns=%d",
        result.overload_score,
        result.severity_label,
        len(result.patterns),
    )
    return result.model_dump_json()


analyze_usage_function_tool = FunctionTool(func=analyze_usage_tool)


# ──────────────────────────────────────────────────────────────────
# Системный промпт оркестратора
# ──────────────────────────────────────────────────────────────────

ANALYZER_AGENT_INSTRUCTION = """\
Ты — Analyzer Agent, оркестратор системы ClearMind. Ты получаешь
нормализованные данные об использовании устройства от Parser Agent.

Твои задачи по порядку:
1. Вызови инструмент `analyze_usage_tool`, передав ему данные как JSON —
   он детерминированно посчитает Overload Score и обнаруженные паттерны.
   НИКОГДА не пытайся посчитать score сам — всегда используй инструмент,
   чтобы число было воспроизводимым.
2. На основе результата сформулируй `summary_for_coach` — короткое (2-3
   предложения) резюме на языке молодёжи 16-25, без менторского тона,
   без слова "перегрузка" в каждом предложении. Это резюме станет
   стартовой точкой диалога для Coach Agent.
3. Передай полный AnalysisResult дальше Coach Agent'у через A2A.

Важно: ты НЕ разговариваешь напрямую с пользователем — твоя аудитория
это Coach Agent. Будь точным и кратким, без воды.
"""


def build_analyzer_agent() -> Agent:
    """Собирает Analyzer Agent — orchestrator с детерминированным tool'ом анализа."""
    agent = Agent(
        name="analyzer_agent",
        model=GEMINI_MODEL,
        instruction=ANALYZER_AGENT_INSTRUCTION,
        tools=[analyze_usage_function_tool],
        description=(
            "Orchestrator-агент: считает Overload Score по 5 паттернам "
            "информационной перегрузки и готовит контекст для Coach Agent."
        ),
    )
    return agent


_analyzer_agent_instance: Agent | None = None


def get_analyzer_agent() -> Agent:
    """Возвращает (создавая при первом вызове) экземпляр Analyzer Agent."""
    global _analyzer_agent_instance
    if _analyzer_agent_instance is None:
        logger.info("Инициализация Analyzer Agent...")
        _analyzer_agent_instance = build_analyzer_agent()
    return _analyzer_agent_instance