"""
a2a/registry.py

Реестр агентов: сопоставляет AgentName с сетевым адресом, по которому
этот агент доступен. В локальной разработке все агенты крутятся на
localhost на разных портах (см. .env: PARSER_AGENT_PORT и т.д.). В Cloud
Run каждый агент — отдельный сервис со своим URL, и регистрация меняется
без переписывания вызывающего кода (см. ANALYZER_AGENT_URL и т.д. — если
заданы, используются вместо localhost).
"""

from __future__ import annotations

import os

from a2a.messages import AgentName


def _resolve_agent_url(agent: AgentName, default_port_env: str) -> str:
    """
    Определяет URL агента: сначала смотрит на явный *_AGENT_URL (для Cloud Run),
    затем падает обратно на localhost:<порт из .env> для локальной разработки.
    """
    url_env_key = f"{agent.value.upper()}_URL"
    explicit_url = os.getenv(url_env_key)
    if explicit_url:
        return explicit_url.rstrip("/")

    port = os.getenv(default_port_env, "8000")
    return f"http://localhost:{port}"


def get_agent_url(agent: AgentName) -> str:
    """Возвращает базовый URL для агента — единая точка входа для A2A клиента."""
    port_env_map = {
        AgentName.PARSER: "PARSER_AGENT_PORT",
        AgentName.ANALYZER: "ANALYZER_AGENT_PORT",
        AgentName.COACH: "COACH_AGENT_PORT",
        AgentName.GUARD: "GUARD_AGENT_PORT",
    }
    return _resolve_agent_url(agent, port_env_map[agent])


# Эндпоинт, который каждый агент-сервер должен реализовать (см. server runner ниже)
A2A_TASK_ENDPOINT = "/a2a/task"
A2A_HEALTH_ENDPOINT = "/a2a/health"