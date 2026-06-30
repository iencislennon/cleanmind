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
                response.raise_for_status()
                result = A2AResult.model_validate(response.json())
        except httpx.HTTPError as exc:
            logger.error("A2A: ошибка при вызове %s: %s", recipient.value, exc)
            return A2AResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error_message=f"Сетевая ошибка при обращении к {recipient.value}: {exc}",
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
            async for event in runner.run_async(
                user_id=task.session_id,
                session_id=task.session_id,
                new_message=task.payload,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text or ""

            return A2AResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                result_payload=final_response_text,
            )
        except Exception as exc:  # noqa: BLE001 — нужно поймать всё, чтобы вернуть A2AResult
            logger.exception("A2A сервер [%s]: ошибка обработки задачи", agent_name.value)
            return A2AResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error_message=str(exc),
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
    Запускает полный конвейер Parser -> Guard (consent) -> Analyzer -> Coach
    через A2A, от лица оркестратора (используется api/main.py).

    Каждый шаг — отдельный A2A вызов, поэтому если какой-то агент развёрнут
    отдельно (Cloud Run), вызывающему коду (FastAPI backend) ничего менять
    не нужно — он просто видит A2AClient.
    """
    client = A2AClient(sender=AgentName.GUARD)  # backend выступает от имени Guard как координатора входа

    # Шаг 1: Guard регистрирует consent gate и проверяет файл ДО парсинга
    guard_pre_check = await client.send_task(
        recipient=AgentName.GUARD,
        task_type="pre_parse_check",
        payload=raw_file_payload,
        session_id=session_id,
    )
    if guard_pre_check.status != TaskStatus.COMPLETED:
        return guard_pre_check

    # Шаг 2: Parser Agent читает и нормализует файл
    parser_client = A2AClient(sender=AgentName.PARSER)
    parse_result = await parser_client.send_task(
        recipient=AgentName.PARSER,
        task_type="parse_file",
        payload=raw_file_payload,
        session_id=session_id,
    )
    if parse_result.status != TaskStatus.COMPLETED or not parse_result.result_payload:
        return parse_result

    # Шаг 3: Analyzer Agent считает Overload Score
    analyzer_client = A2AClient(sender=AgentName.ANALYZER)
    analysis_result = await analyzer_client.send_task(
        recipient=AgentName.ANALYZER,
        task_type="analyze_usage",
        payload=parse_result.result_payload,
        session_id=session_id,
    )
    if analysis_result.status != TaskStatus.COMPLETED or not analysis_result.result_payload:
        return analysis_result

    # Шаг 4: Coach Agent готовит стартовое сообщение диалога с планом
    coach_client = A2AClient(sender=AgentName.COACH)
    coach_result = await coach_client.send_task(
        recipient=AgentName.COACH,
        task_type="start_conversation",
        payload=analysis_result.result_payload,
        session_id=session_id,
    )
    return coach_result