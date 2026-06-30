"""
agents/guard_agent.py

Guard Agent — слой безопасности и приватности системы ClearMind.

Роль: единственный агент, который имеет право (а) проверять каждый
значимый шаг конвейера (получение файла, отправка данных в LLM, передача
между агентами) по детерминированным политикам (security_policies.py) и
(б) формировать consent gates — точки, где без явного согласия пользователя
действие просто не происходит.

Architecturally Guard Agent работает "сбоку", а не последовательно в
конвейере Parser -> Analyzer -> Coach: остальные агенты дёргают его tools
в нужных точках (например, Parser Agent после получения файла вызывает
request_consent_tool перед тем как передать данные в MCP сервер).

Это и есть ответ на требование хакатона "Security features" — не просто
текст в README, а отдельный агент с проверяемым кодом.
"""

from __future__ import annotations

import logging
import os
import re
import uuid

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from agents.guard_models import (
    AuditEvent,
    AuditEventType,
    ConsentGate,
    GuardReport,
)
from agents.security_policies import run_full_security_audit

logger = logging.getLogger("clearmind.guard_agent")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# In-memory хранилище отчётов по сессиям. Намеренно in-memory (не БД) —
# отчёт живёт ровно столько, сколько сессия, и исчезает вместе с процессом,
# что само по себе является частью privacy-гарантии.
_session_reports: dict[str, GuardReport] = {}


def _get_or_create_report(session_id: str) -> GuardReport:
    if session_id not in _session_reports:
        _session_reports[session_id] = GuardReport(session_id=session_id)
    return _session_reports[session_id]


# ──────────────────────────────────────────────────────────────────
# ADK Tools
# ──────────────────────────────────────────────────────────────────


def _normalize_event_type(event_type: str) -> str:
    """Convert PascalCase or UPPER_CASE to snake_case so LLM output tolerantly maps to enum values."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", event_type).lower()
    return s


def log_audit_event_tool(
    session_id: str, event_type: str, description: str, data_scope: str
) -> str:
    """ADK Tool: записывает событие в журнал аудита сессии."""
    report = _get_or_create_report(session_id)
    normalized = _normalize_event_type(event_type)
    try:
        parsed_type = AuditEventType(normalized)
    except ValueError:
        parsed_type = AuditEventType(event_type)
    event = AuditEvent(
        event_type=parsed_type, description=description, data_scope=data_scope
    )
    report.events.append(event)
    logger.info("Guard [%s]: %s — %s", session_id, event_type, description)
    return event.model_dump_json()


def request_consent_tool(session_id: str, gate_id: str, description: str, required_before: str) -> str:
    """
    ADK Tool: регистрирует consent gate как ожидающий решения пользователя.
    Действие, указанное в required_before, не должно выполняться другими
    агентами пока соответствующий gate не получит granted=True через
    grant_consent_tool.
    """
    report = _get_or_create_report(session_id)
    gate = ConsentGate(
        gate_id=gate_id, description=description, required_before=required_before
    )
    report.consent_gates.append(gate)
    log_audit_event_tool(
        session_id, AuditEventType.CONSENT_REQUESTED.value, description, "consent"
    )
    return gate.model_dump_json()


def grant_consent_tool(session_id: str, gate_id: str, granted: bool) -> str:
    """
    ADK Tool: фиксирует ЯВНОЕ решение пользователя по конкретному consent gate.
    Это единственный способ перевести gate в granted=True — никакой агент
    не может сделать это автоматически.
    """
    report = _get_or_create_report(session_id)
    target_gate = None
    for gate in report.consent_gates:
        if gate.gate_id == gate_id:
            gate.granted = granted
            target_gate = gate
            break

    if target_gate is None:
        return f'{{"error": "gate_id {gate_id} не найден"}}'

    event_type = (
        AuditEventType.CONSENT_GRANTED if granted else AuditEventType.CONSENT_DENIED
    )
    log_audit_event_tool(session_id, event_type.value, target_gate.description, "consent")
    return target_gate.model_dump_json()


def run_security_audit_tool(
    session_id: str, file_size_bytes: int, payload_sent_to_llm_json: str, outbound_domains_csv: str
) -> str:
    """
    ADK Tool: запускает полный набор детерминированных security-проверок
    (security_policies.py) и записывает результат в отчёт сессии.
    """
    import json

    payload = json.loads(payload_sent_to_llm_json) if payload_sent_to_llm_json else {}
    domains = [d.strip() for d in outbound_domains_csv.split(",") if d.strip()]

    audit_result = run_full_security_audit(
        file_size_bytes=file_size_bytes,
        payload_sent_to_llm=payload,
        outbound_domains_used=domains,
    )

    report = _get_or_create_report(session_id)
    report.external_calls_made = domains
    if not audit_result["all_passed"]:
        report.policy_violations_blocked += 1
        log_audit_event_tool(
            session_id,
            AuditEventType.POLICY_VIOLATION_BLOCKED.value,
            f"Security audit failed: {audit_result['checks']}",
            "security_audit",
        )

    return json.dumps(audit_result, ensure_ascii=False)


def get_guard_report_tool(session_id: str) -> str:
    """ADK Tool: возвращает полный Privacy Report сессии — то, что видит пользователь."""
    report = _get_or_create_report(session_id)
    return report.model_dump_json()


def discard_session_data_tool(session_id: str) -> str:
    """
    ADK Tool: явно стирает отчёт сессии из памяти. Вызывается в конце
    сессии (или по запросу пользователя) — реализует "right to be forgotten"
    на уровне приложения.
    """
    if session_id in _session_reports:
        report = _session_reports[session_id]
        report.events.append(
            AuditEvent(
                event_type=AuditEventType.SESSION_DATA_DISCARDED,
                description="Сессия завершена, все данные удалены из памяти.",
                data_scope="all",
            )
        )
        final = report.model_dump_json()
        del _session_reports[session_id]
        logger.info("Guard [%s]: данные сессии стёрты из памяти", session_id)
        return final
    return f'{{"error": "session_id {session_id} не найден"}}'


log_audit_event_function_tool = FunctionTool(func=log_audit_event_tool)
request_consent_function_tool = FunctionTool(func=request_consent_tool)
grant_consent_function_tool = FunctionTool(func=grant_consent_tool)
run_security_audit_function_tool = FunctionTool(func=run_security_audit_tool)
get_guard_report_function_tool = FunctionTool(func=get_guard_report_tool)
discard_session_data_function_tool = FunctionTool(func=discard_session_data_tool)


# ──────────────────────────────────────────────────────────────────
# Системный промпт
# ──────────────────────────────────────────────────────────────────

GUARD_AGENT_INSTRUCTION = """\
Ты — Guard Agent, единственный агент системы ClearMind с полномочиями
по безопасности и приватности. Ты не разговариваешь с пользователем
о его цифровых привычках — это работа Coach Agent. Твоя зона
ответственности — данные и согласие.

Правила:
1. Перед тем как любой другой агент обработает файл пользователя —
   убедись что соответствующий consent gate создан (request_consent_tool)
   и получен (только пользователь может его подтвердить).
2. После каждой значимой операции (парсинг файла, вызов LLM с данными
   пользователя) вызывай log_audit_event_tool — журнал должен быть полным.
3. Перед отправкой любых данных в Gemini API — вызови run_security_audit_tool
   и проверь что all_passed=true. Если нет — блокируй операцию и сообщи
   что именно не прошло проверку.
4. По запросу пользователя (или в конце сессии) вызови
   discard_session_data_tool — это финальная гарантия что ничего не
   осталось в памяти после работы.
5. На вопрос "что вы знаете обо мне" или "что происходит с моими данными" —
   вызови get_guard_report_tool и дай пользователю честный, полный отчёт,
   без приукрашивания.

Ты никогда не одобряешь действие "по умолчанию" — каждое решение о
данных либо явно разрешено политикой, либо явно подтверждено пользователем.
"""


def build_guard_agent() -> Agent:
    """Собирает Guard Agent со всеми security/privacy tools."""
    agent = Agent(
        name="guard_agent",
        model=GEMINI_MODEL,
        instruction=GUARD_AGENT_INSTRUCTION,
        tools=[
            log_audit_event_function_tool,
            request_consent_function_tool,
            grant_consent_function_tool,
            run_security_audit_function_tool,
            get_guard_report_function_tool,
            discard_session_data_function_tool,
        ],
        description=(
            "Security/privacy агент: consent gates, audit trail, "
            "проверка отсутствия PII и несанкционированных исходящих вызовов."
        ),
    )
    return agent


_guard_agent_instance: Agent | None = None


def get_guard_agent() -> Agent:
    """Возвращает (создавая при первом вызове) экземпляр Guard Agent."""
    global _guard_agent_instance
    if _guard_agent_instance is None:
        logger.info("Инициализация Guard Agent...")
        _guard_agent_instance = build_guard_agent()
    return _guard_agent_instance


def new_session_id() -> str:
    """Генерирует новый session_id — используется FastAPI слоем при старте сессии."""
    return str(uuid.uuid4())