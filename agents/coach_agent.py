"""
agents/coach_agent.py

Coach Agent — conversational агент системы ClearMind.

Роль: единственный агент, который РАЗГОВАРИВАЕТ с пользователем напрямую.
Получает AnalysisResult от Analyzer Agent (через A2A), ведёт короткий диалог
(3-5 вопросов) чтобы понять контекст пользователя, строит DetoxPlan через
plan_builder.py, и реализует human-in-the-loop: каждый шаг плана пользователь
явно принимает или отклоняет — агент НИКОГДА не считает шаг активным
автоматически.

Тон специально не менторский — это прямое требование к аудитории 16-25,
которая отторгает поучительный тон wellness-приложений.
"""

from __future__ import annotations

import logging
import os

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from agents.analyzer_models import AnalysisResult
from agents.coach_models import DetoxPlan, StepStatus
from agents.plan_builder import build_detox_plan

logger = logging.getLogger("clearmind.coach_agent")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


# ──────────────────────────────────────────────────────────────────
# ADK Tools — детерминированные операции, которые LLM-агент вызывает
# ──────────────────────────────────────────────────────────────────


def create_plan_tool(analysis_result_json: str, user_context: str = "") -> str:
    """
    ADK Tool: строит DetoxPlan из результата анализа + контекста диалога.
    Шаги создаются со статусом PROPOSED — ничего не считается принятым
    до явного решения пользователя (см. update_step_status_tool).
    """
    analysis = AnalysisResult.model_validate_json(analysis_result_json)
    plan = build_detox_plan(analysis, user_context=user_context)
    logger.info("Coach: создан план %s с %d шагами (все PROPOSED)", plan.plan_id, len(plan.steps))
    return plan.model_dump_json()


def update_step_status_tool(plan_json: str, step_id: str, new_status: str) -> str:
    """
    ADK Tool: human-in-the-loop ядро системы.

    Обновляет статус ОДНОГО конкретного шага на основе ЯВНОГО решения
    пользователя ("да", "не буду", "сделал"). Агент никогда не вызывает
    этот tool сам по себе без соответствующей реплики пользователя —
    это прописано в системном промпте ниже.
    """
    plan = DetoxPlan.model_validate_json(plan_json)
    status = StepStatus(new_status)

    found = False
    for step in plan.steps:
        if step.step_id == step_id:
            step.status = status
            found = True
            break

    if not found:
        logger.warning("Coach: step_id %s не найден в плане %s", step_id, plan.plan_id)

    logger.info(
        "Coach: шаг %s -> %s (принято шагов всего: %d/%d)",
        step_id,
        status.value,
        plan.accepted_steps_count,
        len(plan.steps),
    )
    return plan.model_dump_json()


create_plan_function_tool = FunctionTool(func=create_plan_tool)
update_step_status_function_tool = FunctionTool(func=update_step_status_tool)


# ──────────────────────────────────────────────────────────────────
# Системный промпт — тон и human-in-the-loop правила
# ──────────────────────────────────────────────────────────────────

COACH_AGENT_INSTRUCTION = """\
Ты — Coach Agent в системе ClearMind. Ты говоришь с человеком 16-25 лет
напрямую. Твой тон: на равных, без менторства, без фраз вроде "тебе нужно"
или "ты должен". Используй язык собеседника, короткие фразы, без воды.

Последовательность действий:
1. У тебя есть AnalysisResult от Analyzer Agent с summary_for_coach.
   Начни разговор с этого summary, но переформулируй живо, не зачитывай как отчёт.
2. Задай 3-5 коротких вопросов, чтобы понять контекст: учёба, работа, или
   просто привычка от скуки. Не дави, если человек не хочет отвечать подробно —
   двигайся дальше с тем что есть.
3. Вызови `create_plan_tool` передав AnalysisResult и собранный user_context.
   Это создаст план с шагами в статусе PROPOSED.
4. Предложи план ПО ОДНОМУ шагу, не вываливай все 5 сразу. После каждого шага
   спроси явное решение: "норм, попробуешь?" / аналог.
5. КРИТИЧЕСКИ ВАЖНО (human-in-the-loop): когда пользователь отвечает на
   конкретный шаг — ТОЛЬКО ТОГДА вызови `update_step_status_tool` с этим
   step_id и статусом accepted/rejected. Никогда не помечай шаг как accepted
   по умолчанию или потому что "это же полезно". Решение всегда явное и
   принадлежит пользователю.
6. В конце — короткое резюме: сколько шагов приняли, когда план "стартует".
   Без поздравлений в духе "ты молодец" — просто факт.

Если пользователь говорит что хочет остановиться или не готов — уважай это,
не уговаривай, предложи вернуться позже.
"""


def build_coach_agent() -> Agent:
    """Собирает Coach Agent с tools для построения плана и human-in-the-loop апдейтов."""
    agent = Agent(
        name="coach_agent",
        model=GEMINI_MODEL,
        instruction=COACH_AGENT_INSTRUCTION,
        tools=[create_plan_function_tool, update_step_status_function_tool],
        description=(
            "Conversational агент: ведёт диалог с пользователем, строит "
            "7-дневный план детоксикации и реализует human-in-the-loop "
            "подтверждение каждого шага."
        ),
    )
    return agent


_coach_agent_instance: Agent | None = None


def get_coach_agent() -> Agent:
    """Возвращает (создавая при первом вызове) экземпляр Coach Agent."""
    global _coach_agent_instance
    if _coach_agent_instance is None:
        logger.info("Инициализация Coach Agent...")
        _coach_agent_instance = build_coach_agent()
    return _coach_agent_instance