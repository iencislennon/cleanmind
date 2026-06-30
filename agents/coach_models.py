"""
agents/coach_models.py

Модели для плана цифровой детоксикации и состояния диалога с пользователем.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    """Статус шага плана — central для human-in-the-loop механики."""

    PROPOSED = "proposed"  # предложен агентом, ждёт решения пользователя
    ACCEPTED = "accepted"  # пользователь согласился
    REJECTED = "rejected"  # пользователь отклонил
    COMPLETED = "completed"  # пользователь отметил выполненным


class DetoxStep(BaseModel):
    """Один конкретный, измеримый шаг плана детоксикации."""

    step_id: str
    day: int = Field(ge=1, le=7, description="День плана, 1-7")
    title: str
    description: str
    related_pattern_id: str = Field(
        description="К какому паттерну из AnalysisResult относится этот шаг"
    )
    measurable_target: str = Field(
        description="Конкретная измеримая цель, например 'Без телефона после 23:00'"
    )
    status: StepStatus = StepStatus.PROPOSED


class DetoxPlan(BaseModel):
    """Полный 7-дневный план — то, что Coach Agent строит и пользователь утверждает."""

    plan_id: str
    overload_score_at_creation: int
    steps: list[DetoxStep] = Field(default_factory=list)
    user_context: str = Field(
        default="", description="Контекст из диалога: учёба/работа/скука и т.д."
    )

    @property
    def accepted_steps_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.ACCEPTED)

    @property
    def is_fully_reviewed(self) -> bool:
        """True когда пользователь принял решение по каждому шагу (не PROPOSED)."""
        return all(s.status != StepStatus.PROPOSED for s in self.steps)


class CoachMessage(BaseModel):
    """Одно сообщение в диалоге Coach Agent <-> пользователь."""

    role: str = Field(description="'agent' или 'user'")
    content: str
    proposed_plan: DetoxPlan | None = None