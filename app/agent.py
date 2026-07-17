"""Gemini-powered agent loop.

Manual function-calling loop (rather than the SDK's automatic mode) so every
tool call and result is captured in a trace the UI can display — the agent's
reasoning is visible, not a black box.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import errors, types

from .prompts import SYSTEM_PROMPT
from .tools import TOOL_DECLARATIONS, execute_tool

# Tried in order. The -latest aliases track Google's current models (so the
# demo survives model retirements); the rest absorb 503s when the newest
# model is under heavy demand on the free tier.
MODEL_CHAIN = [
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
]
MAX_STEPS = 8


def _generate(client: genai.Client, contents, config) -> types.GenerateContentResponse:
    """Call Gemini, falling through the model chain on availability errors."""
    last_error: Exception | None = None
    for model in MODEL_CHAIN:
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except errors.APIError as exc:
            if exc.code in (404, 429, 503):
                last_error = exc
                continue
            raise
    raise last_error  # every model in the chain was unavailable


def run_agent(message: str, history: list[dict] | None = None) -> dict:
    """Run one agent turn. Returns {"reply": str, "trace": [tool events]}.

    `history` is prior turns as [{"role": "user"|"assistant", "text": str}].
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    contents: list[types.Content] = []
    for turn in history or []:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=turn.get("text", ""))])
        )
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
        temperature=0.2,
    )

    trace: list[dict] = []
    for _ in range(MAX_STEPS):
        response = _generate(client, contents, config)
        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        calls = [p.function_call for p in parts if p.function_call]

        if not calls:
            return {"reply": (response.text or "").strip(), "trace": trace}

        contents.append(candidate.content)
        response_parts = []
        for call in calls:
            args = dict(call.args or {})
            result = execute_tool(call.name, args)
            trace.append({"tool": call.name, "args": args, "result": result})
            response_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=response_parts))

    return {
        "reply": (
            "I wasn't able to resolve this automatically, so I'm handing it to a "
            "human specialist who will follow up with you."
        ),
        "trace": trace,
    }
