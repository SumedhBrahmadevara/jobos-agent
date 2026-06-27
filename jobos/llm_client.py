from __future__ import annotations

import json
from typing import TypeVar, Type

from pydantic import BaseModel

from jobos.config import OPENAI_API_KEY, JOBOS_MODEL, JOBOS_OFFLINE_MODE

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    pass


def llm_is_available() -> bool:
    return bool(OPENAI_API_KEY) and not JOBOS_OFFLINE_MODE


def structured_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    output_model: Type[T],
    schema_name: str,
    model: str | None = None,
) -> T:
    """Call OpenAI Responses API and validate the result with Pydantic.

    This project keeps all LLM access behind this one function so Claude/Codex can
    update the API syntax later without touching every agent.
    """
    if not llm_is_available():
        raise LLMUnavailable("OPENAI_API_KEY is missing or JOBOS_OFFLINE_MODE=true.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMUnavailable("Install dependencies with: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=OPENAI_API_KEY)
    schema = output_model.model_json_schema()

    response = client.responses.create(
        model=model or JOBOS_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    )

    raw = getattr(response, "output_text", None)
    if not raw:
        # Defensive fallback for SDK shape changes.
        raw = json.dumps(response.model_dump())

    return output_model.model_validate_json(raw)
