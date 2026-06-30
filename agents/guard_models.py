"""
agents/guard_models.py

Модели для журнала аудита (audit trail) и consent gates.
Guard Agent использует их чтобы и контролировать действия других агентов,
и предоставлять пользователю прозрачный отчёт "что именно происходило
с вашими данными".
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    FILE_RECEIVED = "file_received"
    FILE_PARSED = "file_parsed"
    DATA_SENT_TO_AGENT = "data_sent_to_agent"
    DATA_SENT_TO_LLM = "data_sent_to_llm"
    SESSION_DATA_DISCARDED = "session_data_discarded"
    CONSENT_REQUESTED = "consent_requested"
    CONSENT_GRANTED = "consent_granted"
    CONSENT_DENIED = "consent_denied"
    POLICY_VIOLATION_BLOCKED = "policy_violation_blocked"


class AuditEvent(BaseModel):
    """Одна запись в журнале — что произошло с данными пользователя и когда."""

    event_type: AuditEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str
    data_scope: str = Field(
        description="Что именно затронуто: 'raw_file', 'aggregated_metrics', 'plan' и т.д."
    )


class ConsentGate(BaseModel):
    """
    Один пункт согласия, который должен явно подтвердить пользователь
    ДО того как соответствующее действие будет разрешено.
    """

    gate_id: str
    description: str
    required_before: str = Field(description="Какое действие заблокировано без согласия")
    granted: bool = False


class GuardReport(BaseModel):
    """Итоговый отчёт Guard Agent — то, что показывается пользователю как 'Privacy Report'."""

    session_id: str
    events: list[AuditEvent] = Field(default_factory=list)
    consent_gates: list[ConsentGate] = Field(default_factory=list)
    raw_data_persisted: bool = False
    external_calls_made: list[str] = Field(
        default_factory=list, description="Любые исходящие сетевые вызовы кроме LLM API"
    )
    policy_violations_blocked: int = 0

    @property
    def is_clean(self) -> bool:
        """True если данные не сохранялись, нет лишних внешних вызовов, нет нарушений."""
        return (
            not self.raw_data_persisted
            and len(self.external_calls_made) == 0
            and self.policy_violations_blocked == 0
        )