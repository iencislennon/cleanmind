from __future__ import annotations

import os


def get_model():
    """Return the right model object for ADK based on GEMINI_MODEL env var.

    Gemini model strings are passed as-is (ADK handles them natively).
    Everything else (openai/*, groq/*, etc.) is wrapped in LiteLlm.
    """
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    if model_name.startswith("gemini"):
        return model_name
    from google.adk.models.lite_llm import LiteLlm
    return LiteLlm(model=model_name)
