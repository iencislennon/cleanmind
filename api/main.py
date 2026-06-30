"""
api/main.py

FastAPI backend — единственная точка входа для фронтенда.

Архитектурно этот файл выполняет две роли:
1. Хост для A2A-роутеров всех четырёх агентов в режиме локальной
   разработки (один процесс, один порт, разные пути) — см. include_router
   ниже. В Cloud Run каждый агент запускается как отдельный сервис своим
   entrypoint'ом (см. agents/*_server.py, который мы добавим на стадии деплоя),
   а api/main.py обращается к ним по сети через A2AClient.
2. Прикладной REST API для фронтенда: загрузка файла, запуск конвейера,
   чат с Coach Agent, human-in-the-loop решения по шагам плана, Privacy Report.

Запуск локально:
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

# Google ADK reads GOOGLE_API_KEY; alias from GEMINI_API_KEY if set
if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from a2a.messages import AgentName, TaskStatus
from a2a.protocol import A2AClient, build_a2a_router, run_full_pipeline
from agents.analyzer_agent import get_analyzer_agent
from agents.coach_agent import get_coach_agent
from agents.guard_agent import get_guard_agent, new_session_id
from agents.guard_models import GuardReport
from agents.parser_agent import get_parser_agent
from api.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    PipelineStatusResponse,
    PrivacyReportResponse,
    StartSessionResponse,
    StepDecisionRequest,
    UploadFileRequest,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("clearmind.api")

app = FastAPI(
    title="ClearMind API",
    description="Information Overload Shield — мультиагентный backend",
    version="0.1.0",
)

# CORS открыт для фронтенда (Refero template). В проде стоит сузить до
# конкретного домена — оставлено широким на хакатон-период ради скорости разработки.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────
# Регистрация A2A-роутеров каждого агента (для локального single-process режима)
# ──────────────────────────────────────────────────────────────────

app.include_router(
    build_a2a_router(get_parser_agent(), AgentName.PARSER),
    prefix="/agents/parser",
    tags=["a2a"],
)
app.include_router(
    build_a2a_router(get_analyzer_agent(), AgentName.ANALYZER),
    prefix="/agents/analyzer",
    tags=["a2a"],
)
app.include_router(
    build_a2a_router(get_coach_agent(), AgentName.COACH),
    prefix="/agents/coach",
    tags=["a2a"],
)
app.include_router(
    build_a2a_router(get_guard_agent(), AgentName.GUARD),
    prefix="/agents/guard",
    tags=["a2a"],
)


# ──────────────────────────────────────────────────────────────────
# Прикладные эндпоинты для фронтенда
# ──────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    """Общий health-check всего backend'а — используется при деплое на Cloud Run."""
    return {"status": "ok", "service": "clearmind-api"}


@app.post("/session/start", response_model=StartSessionResponse)
async def start_session() -> StartSessionResponse:
    """
    Создаёт новую сессию пользователя. session_id используется во ВСЕХ
    последующих вызовах — это та же нить, по которой Guard Agent ведёт
    журнал аудита.
    """
    session_id = new_session_id()
    logger.info("Новая сессия создана: %s", session_id)
    return StartSessionResponse(session_id=session_id)


@app.post("/pipeline/run", response_model=PipelineStatusResponse)
async def run_pipeline(session_id: str, request: UploadFileRequest) -> PipelineStatusResponse:
    """
    Запускает полный конвейер: Guard (consent+проверка) -> Parser -> Analyzer
    -> Coach, через A2A. Это основной эндпоинт, который вызывается сразу
    после загрузки файла пользователем.
    """
    result = await run_full_pipeline(
        session_id=session_id,
        raw_file_payload=request.model_dump_json(),
    )

    if result.status != TaskStatus.COMPLETED:
        return PipelineStatusResponse(
            session_id=session_id,
            status=result.status.value,
            error_message=result.error_message or "Конвейер остановлен без явной ошибки.",
        )

    return PipelineStatusResponse(
        session_id=session_id,
        status="completed",
        coach_message=result.result_payload,
    )


@app.post("/chat/message", response_model=ChatMessageResponse)
async def send_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    """
    Отправляет сообщение пользователя Coach Agent'у в рамках существующей
    сессии (диалог после того как план уже предложен).
    """
    client = A2AClient(sender=AgentName.COACH)
    result = await client.send_task(
        recipient=AgentName.COACH,
        task_type="user_message",
        payload=request.message,
        session_id=request.session_id,
    )

    if result.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=502, detail=result.error_message or "Coach Agent недоступен")

    return ChatMessageResponse(
        session_id=request.session_id,
        agent_reply=result.result_payload or "",
    )


@app.post("/plan/step-decision")
async def submit_step_decision(request: StepDecisionRequest) -> dict:
    """
    Human-in-the-loop эндпоинт: пользователь явно принимает/отклоняет/
    завершает конкретный шаг плана. Это прямой вызов в Coach Agent,
    результат которого (обновлённый план) Coach Agent логирует через
    Guard Agent отдельно — см. coach_agent.py update_step_status_tool.
    """
    client = A2AClient(sender=AgentName.COACH)
    payload = request.model_dump_json()
    result = await client.send_task(
        recipient=AgentName.COACH,
        task_type="step_decision",
        payload=payload,
        session_id=request.session_id,
    )

    if result.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=502, detail=result.error_message or "Не удалось обновить шаг плана")

    return {"status": "ok", "updated_plan": result.result_payload}


@app.get("/privacy/report/{session_id}", response_model=PrivacyReportResponse)
async def get_privacy_report(session_id: str) -> PrivacyReportResponse:
    """
    Возвращает Privacy Report сессии напрямую из Guard Agent — пользователь
    в любой момент может увидеть, что именно происходило с его данными.
    """
    from agents.guard_agent import get_guard_report_tool

    report_json = get_guard_report_tool(session_id)
    report = GuardReport.model_validate_json(report_json)

    return PrivacyReportResponse(
        session_id=report.session_id,
        is_clean=report.is_clean,
        events_count=len(report.events),
        raw_data_persisted=report.raw_data_persisted,
        external_calls_made=report.external_calls_made,
        policy_violations_blocked=report.policy_violations_blocked,
    )


@app.delete("/session/{session_id}")
async def end_session(session_id: str) -> dict:
    """
    Явное завершение сессии пользователем — вызывает discard_session_data_tool
    у Guard Agent, стирая всё из памяти. Это и есть "Zero Data Persistence"
    из питча, доведённое до конкретного API-вызова, а не только текста в README.
    """
    from agents.guard_agent import discard_session_data_tool

    result = discard_session_data_tool(session_id)
    logger.info("Сессия %s завершена пользователем, данные стёрты", session_id)
    return {"status": "session_ended", "final_report": result}


def main() -> None:
    """Точка входа для команды `clearmind` (см. pyproject.toml [project.scripts])."""
    import uvicorn

    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=os.getenv("DEBUG") == "true")


if __name__ == "__main__":
    main()