"""Thin wrapper around the Anthropic Messages API for structured extraction.

Isolated behind this single function so app/services/ingestion.py (and its
tests) never need real API credentials: tests monkeypatch extract_structured
directly instead of mocking the SDK.
"""

import json

import anthropic

from app.core.config import get_settings

MODEL = "claude-opus-5"


def extract_structured(system_prompt: str, user_content: str, json_schema: dict) -> dict:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": json_schema}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)
