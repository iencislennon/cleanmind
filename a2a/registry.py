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


_LOCAL_PATH_PREFIX: dict[AgentName, str] = {
    AgentName.PARSER: "/agents/parser",
    AgentName.ANALYZER: "/agents/analyzer",
    AgentName.COACH: "/agents/coach",
    AgentName.GUARD: "/agents/guard",
}


def _resolve_agent_url(agent: AgentName, default_port_env: str) -> str:
    """
    Determines the agent URL: first checks for an explicit *_URL env var (Cloud Run),
    then falls back to localhost:<port> + path prefix for local single-process mode.
    In Cloud Run each agent is a separate service at its own root, so no prefix is needed.
    """
    url_env_key = f"{agent.value.upper()}_URL"
    explicit_url = os.getenv(url_env_key)
    if explicit_url:
        return explicit_url.rstrip("/")

    port = os.getenv(default_port_env, "8000")
    path_prefix = _LOCAL_PATH_PREFIX.get(agent, "")
    return f"http://localhost:{port}{path_prefix}"


def get_agent_url(agent: AgentName) -> str:
    """Returns the base URL for an agent — single entry point for the A2A client."""
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