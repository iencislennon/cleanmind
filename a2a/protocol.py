"""
a2a/protocol.py

Главный модуль A2A коммуникации. Содержит:

1. A2AClient — отправляет задачи от одного агента к другому через HTTP.
2. a2a_server() — фабрика FastAPI-роутера, который оборачивает ЛЮБОЙ
   ADK-агент (Parser, Analyzer, Coach, Guard) в A2A-совместимый HTTP-сервис
   с эндпоинтами /a2a/task и /a2a/health.
3. Высокоуровневые orchestration-функции (run_pipeline_step), которые
   использует Analyzer Agent как оркестратор всего конвейера.

Почему так: ADK сам по себе не диктует транспорт между агентами — это
именно то, для чего существует A2A. Мы оборачиваем агентов в тонкий
HTTP-слой, чтобы они могли общаться единообразно вне зависимости от того,
бегут ли все четыре в одном docker-compose локально или как четыре
отдельных Cloud Run сервиса.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

from a2a.messages import A2AResult, A2ATask, AgentName, TaskStatus
from a2a.registry import A2A_HEALTH_ENDPOINT, A2A_TASK_ENDPOINT, get_agent_url

logger = logging.getLogger("clearmind.a2a")

A2A_TIMEOUT_SECONDS = 30.0


# ──────────────────────────────────────────────────────────────────
# Клиент: отправка задач другим агентам
# ──────────────────────────────────────────────────────────────────


class A2AClient:
    """
    HTTP-клиент для отправки A2ATask от агента-отправителя к агенту-получателю.

    Используется, например, внутри Analyzer Agent чтобы передать результат
    Coach Agent'у, или внутри любого агента чтобы спросить разрешения у
    Guard Agent перед выполнением чувствительной операции.
    """

    def __init__(self, sender: AgentName, timeout: float = A2A_TIMEOUT_SECONDS) -> None:
        self.sender = sender
        self.timeout = timeout

    async def send_task(
        self,
        recipient: AgentName,
        task_type: str,
        payload: str,
        session_id: str,
    ) -> A2AResult:
        """
        Отправляет задачу агенту-получателю и дожидается результата.

        В случае сетевой ошибки или таймаута возвращает A2AResult со
        статусом FAILED, а не бросает исключение — вызывающий оркестратор
        (Analyzer Agent) сам решает, что делать с упавшим шагом конвейера.
        """
        task = A2ATask(
            session_id=session_id,
            sender=self.sender,
            recipient=recipient,
            task_type=task_type,
            payload=payload,
        )

        url = get_agent_url(recipient) + A2A_TASK_ENDPOINT
        logger.info(
            "A2A: %s -> %s, task_type=%s, task_id=%s",
            self.sender.value,
            recipient.value,
            task_type,
            task.task_id,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=task.model_dump(mode="json"))
                if response.status_code >= 400:
                    body = response.text[:500]
                    logger.error("A2A: HTTP %s от %s: %s", response.status_code, recipient.value, body)
                    return A2AResult(
                        task_id=task.task_id,
                        status=TaskStatus.FAILED,
                        error_message=f"HTTP {response.status_code} from {recipient.value}: {body}",
                    )
                result = A2AResult.model_validate(response.json())
        except httpx.HTTPError as exc:
            logger.error("A2A: network error calling %s: %s", recipient.value, exc)
            return A2AResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error_message=f"Network error calling {recipient.value}: {exc}",
            )
        except Exception as exc:
            logger.error("A2A: unexpected error calling %s: %s", recipient.value, exc, exc_info=True)
            return A2AResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error_message=f"Unexpected error calling {recipient.value}: {exc}",
            )

        logger.info(
            "A2A: получен результат от %s, статус=%s", recipient.value, result.status.value
        )
        return result

    async def check_health(self, recipient: AgentName) -> bool:
        """Проверяет, что агент-получатель жив — используется при старте пайплайна."""
        url = get_agent_url(recipient) + A2A_HEALTH_ENDPOINT
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except httpx.HTTPError:
            return False


# ──────────────────────────────────────────────────────────────────
# Сервер: оборачивает ADK-агент в A2A-совместимый HTTP-роутер
# ──────────────────────────────────────────────────────────────────


def build_a2a_router(agent: Agent, agent_name: AgentName) -> APIRouter:
    """
    Создаёт FastAPI APIRouter с эндпоинтами /a2a/task и /a2a/health для
    переданного ADK-агента.

    Это позволяет каждому агенту (parser_agent.py, analyzer_agent.py и т.д.)
    одновременно быть (а) ADK Agent с tools и LLM-логикой, и (б) полноценным
    A2A-узлом, к которому можно достучаться по HTTP от других агентов или
    напрямую от FastAPI backend'а (api/main.py).
    """
    router = APIRouter()
    runner = InMemoryRunner(agent=agent, app_name=f"clearmind_{agent_name.value}")
    runner.auto_create_session = True

    @router.get(A2A_HEALTH_ENDPOINT)
    async def health() -> dict:
        return {"agent": agent_name.value, "status": "ok"}

    @router.post(A2A_TASK_ENDPOINT, response_model=A2AResult)
    async def handle_task(task: A2ATask) -> A2AResult:
        if task.recipient != agent_name:
            raise HTTPException(
                status_code=400,
                detail=f"Эта задача адресована {task.recipient.value}, а не {agent_name.value}",
            )

        logger.info(
            "A2A сервер [%s]: получена задача %s от %s",
            agent_name.value,
            task.task_type,
            task.sender.value,
        )

        try:
            # Запускаем ADK-агента с payload задачи как пользовательским вводом.
            # session_id из A2ATask используется как идентификатор ADK-сессии,
            # чтобы Guard Agent мог сопоставить вызовы LLM с конкретной сессией.
            final_response_text = ""
            content = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=task.payload)],
            )
            async for event in runner.run_async(
                user_id=task.session_id,
                session_id=task.session_id,
                new_message=content,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text or ""

            return A2AResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                result_payload=final_response_text,
            )
        except Exception as exc:  # noqa: BLE001
            error_detail = repr(exc) or type(exc).__name__
            logger.exception("A2A server [%s]: task processing error: %s", agent_name.value, error_detail)
            return A2AResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error_message=error_detail,
            )

    return router


# ──────────────────────────────────────────────────────────────────
# Высокоуровневая orchestration-функция для полного конвейера
# ──────────────────────────────────────────────────────────────────


async def run_full_pipeline(
    session_id: str,
    raw_file_payload: str,
) -> A2AResult:
    """
    Pipeline: parse (direct) -> analyze (direct) -> coach (LLM via A2A).

    Parsing and scoring are deterministic Python — no LLM needed, no subprocess.
    Only the coach step calls the LLM.
    """
    import json as _json
    import uuid as _uuid
    from agents.guard_agent import (
        log_audit_event_tool,
        request_consent_tool,
        run_security_audit_tool,
    )
    from agents.guard_models import AuditEventType
    from agents.analyzer_agent import compute_overload_score
    from mcp_server.models import DataSource
    from mcp_server.parsers import parse
    import base64

    task_id = str(_uuid.uuid4())[:8]

    # Step 1: Guard — register consent + security audit (direct tool calls, no LLM)
    request_consent_tool(
        session_id=session_id,
        gate_id=f"consent_{session_id}",
        description="User consents to processing their screen-time export.",
        required_before="parse_file",
    )
    log_audit_event_tool(session_id, AuditEventType.FILE_RECEIVED.value, "File received for processing", "raw_file")

    payload_dict = _json.loads(raw_file_payload)
    file_size = len(base64.b64decode(payload_dict.get("file_content_base64", "")))
    audit_result = _json.loads(run_security_audit_tool(
        session_id=session_id,
        file_size_bytes=file_size,
        payload_sent_to_llm_json="{}",
        outbound_domains_csv="",
    ))
    if not audit_result.get("all_passed", True):
        return A2AResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error_message=f"Security audit failed: {audit_result.get('checks')}",
        )

    # Step 2: Parse (direct, no LLM)
    try:
        source = DataSource(payload_dict["source"])
        raw_bytes = base64.b64decode(payload_dict["file_content_base64"])
        parse_result = parse(source, raw_bytes)
    except Exception as exc:
        return A2AResult(task_id=task_id, status=TaskStatus.FAILED, error_message=f"Parse error: {exc}")

    if not parse_result.success or parse_result.data is None:
        return A2AResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error_message=parse_result.error_message or "File parsing failed — check file format.",
        )

    log_audit_event_tool(session_id, AuditEventType.FILE_PARSED.value, "File parsed successfully", "normalized_data")

    # Step 3: Analyze (direct, no LLM)
    try:
        analysis = compute_overload_score(parse_result.data)
    except Exception as exc:
        return A2AResult(task_id=task_id, status=TaskStatus.FAILED, error_message=f"Analysis error: {exc}")

    log_audit_event_tool(session_id, AuditEventType.DATA_SENT_TO_AGENT.value, "Analysis result sent to Coach", "analysis_result")

    # Step 4: Coach — LLM conversation start (A2A)
    coach_client = A2AClient(sender=AgentName.COACH)
    coach_result = await coach_client.send_task(
        recipient=AgentName.COACH,
        task_type="start_conversation",
        payload=analysis.model_dump_json(),
        session_id=session_id,
    )
    return coach_result