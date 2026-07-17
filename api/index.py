"""FastAPI entrypoint, deployed as a Vercel Python serverless function."""

import sys
from pathlib import Path

# Vercel runs this file from api/; make the repo root importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.agent import run_agent  # noqa: E402
from app.data import TRANSACTIONS, format_inr  # noqa: E402

app = FastAPI(title="FaislaAI", version="1.0.0")


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/scenarios")
def scenarios() -> dict:
    """Sample payments the demo UI offers as one-click scenarios."""
    return {
        "payments": [
            {
                "payment_id": txn["payment_id"],
                "amount_inr": format_inr(txn["amount"]),
                "status": txn["status"],
                "description": txn["description"],
            }
            for txn in TRANSACTIONS.values()
        ]
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    try:
        return run_agent(req.message, [t.model_dump() for t in req.history])
    except Exception as exc:  # surface a friendly error, not a 500 trace
        return {
            "reply": (
                "Sorry — I hit a technical snag while processing that. "
                "Please try again in a moment."
            ),
            "trace": [],
            "error": str(exc),
        }
