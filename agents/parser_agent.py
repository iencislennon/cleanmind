"""
agents/parser_agent.py

Parser Agent — first agent in the ClearMind pipeline.

Parses the user's uploaded file using a direct FunctionTool (no MCP subprocess).
LLM is only involved when the file format is ambiguous or parsing fails.
"""

from __future__ import annotations

import base64
import json
import logging

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from agents.model_utils import get_model
from mcp_server.models import DataSource
from mcp_server.parsers import parse

logger = logging.getLogger("clearmind.parser_agent")

def parse_usage_export(source: str, file_content_base64: str) -> str:
    """
    Parse a screen-time export file and return normalised usage data as JSON.

    Args:
        source: Data source type — one of: apple_screen_time,
                google_digital_wellbeing, tiktok_export, instagram_export.
        file_content_base64: Base64-encoded file content.

    Returns:
        JSON string of ParseResult (success, data, error_message, warnings).
    """
    try:
        raw_bytes = base64.b64decode(file_content_base64)
    except Exception as exc:
        return json.dumps({"success": False, "error_message": f"Base64 decode error: {exc}", "warnings": []})

    try:
        ds = DataSource(source)
    except ValueError:
        return json.dumps({"success": False, "error_message": f"Unknown source: {source}", "warnings": []})

    result = parse(ds, raw_bytes)
    return result.model_dump_json()


parse_usage_export_tool = FunctionTool(func=parse_usage_export)


PARSER_AGENT_INSTRUCTION = """\
You are the Parser Agent in ClearMind. Your only job is to call the
`parse_usage_export` tool with the correct `source` and the base64 file content
you receive, then return the tool result as-is.

Rules:
1. If the source type is already specified in the input JSON, use it directly.
2. Call `parse_usage_export` exactly once with those two arguments.
3. Return the tool result JSON unchanged — do NOT summarise or interpret it.
4. If parsing fails (success: false), report the error_message clearly.
5. Never fabricate or guess data values.
"""


def build_parser_agent() -> Agent:
    agent = Agent(
        name="parser_agent",
        model=get_model(),
        instruction=PARSER_AGENT_INSTRUCTION,
        tools=[parse_usage_export_tool],
        description=(
            "Parses screen-time exports (Screen Time, Digital Wellbeing, "
            "TikTok, Instagram) and returns normalised usage data."
        ),
    )
    return agent


_parser_agent_instance: Agent | None = None


def get_parser_agent() -> Agent:
    global _parser_agent_instance
    if _parser_agent_instance is None:
        logger.info("Initialising Parser Agent...")
        _parser_agent_instance = build_parser_agent()
    return _parser_agent_instance
