"""
api/schemas.py

Pydantic-схемы для HTTP API — то, что видит фронтенд. Отдельно от
внутренних моделей агентов (mcp_server/models.py, agents/*_models.py),
потому что API-контракт должен оставаться стабильным даже если внутренние
модели агентов меняются.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UploadFileRequest(BaseModel):
    """Запрос на загрузку файла экспорта данных."""

    source: str = Field(description="apple_screen_time | google_digital_wellbeing | tiktok_export | instagram_export")
    file_content_base64: str
    filename: str


class StartSessionResponse(BaseModel):
    session_id: str


class PipelineStatusResponse(BaseModel):
    session_id: str
    status: str
    overload_score: int | None = None
    severity_label: str | None = None
    coach_message: str | None = None
    error_message: str | None = None


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class ChatMessageResponse(BaseModel):
    session_id: str
    agent_reply: str


class StepDecisionRequest(BaseModel):
    """Human-in-the-loop: явное решение пользователя по шагу плана."""

    session_id: str
    plan_id: str
    step_id: str
    decision: str = Field(description="accepted | rejected | completed")


class PrivacyReportResponse(BaseModel):
    session_id: str
    is_clean: bool
    events_count: int
    raw_data_persisted: bool
    external_calls_made: list[str]
    policy_violations_blocked: int