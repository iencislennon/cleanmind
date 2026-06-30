"""
a2a/messages.py

Модели сообщений для Agent-to-Agent (A2A) коммуникации.

A2A — это протокол Google для того, чтобы независимые агенты (каждый
со своим процессом, своим портом, потенциально на разных машинах) могли
обмениваться задачами и результатами через стандартизированный HTTP/JSON
контракт, а не через прямые Python-вызовы.

В ClearMind это намеренно: Parser, Analyzer, Coach и Guard агенты могут
быть задеплоены как отдельные Cloud Run сервисы. A2A даёт им общий язык
вне зависимости от того, в одном они процессе сейчас (локальная разработка)
или в четырёх разных контейнерах (продакшн).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    """Имена агентов — используются как идентификаторы в маршрутизации A2A."""

    PARSER = "parser_agent"
    ANALYZER = "analyzer_agent"
    COACH = "coach_agent"
    GUARD = "guard_agent"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED_BY_GUARD = "blocked_by_guard"  # Guard Agent не дал добро


class A2ATask(BaseModel):
    """
    Единица работы, которую один агент передаёт другому через A2A.

    Это аналог "task" в стандарте A2A: у задачи есть отправитель, получатель,
    полезная нагрузка (payload — обычно JSON-сериализованная Pydantic модель
    из mcp_server/models.py, agents/analyzer_models.py и т.д.) и session_id,
    который связывает всю цепочку вызовов одной пользовательской сессии —
    это то же session_id, что видит Guard Agent в своём журнале аудита.
    """

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str
    sender: AgentName
    recipient: AgentName
    task_type: str = Field(description="Например: 'parse_file', 'analyze_usage', 'build_plan'")
    payload: str = Field(description="JSON-строка с данными задачи")
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class A2AResult(BaseModel):
    """Результат выполнения A2ATask — то, что получатель отправляет обратно."""

    task_id: str
    status: TaskStatus
    result_payload: str | None = Field(
        default=None, description="JSON-строка с результатом, если status=completed"
    )
    error_message: str | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))