"""
Autonomous SRE Agent: Self-Healing DevOps System
Agent Service
=============
Built by Vignesh Yadala
https://vigneshyadala.github.io/portfolio | https://github.com/Vigneshyadala

Thin FastAPI wrapper around agent_brain.diagnose_and_heal so the monitor
service (and anything else) can invoke the LangChain agent over HTTP
instead of importing it as a local Python module. This is what turns the
"agent_brain.py script" from Phase 1 into a real microservice that
docker-compose can orchestrate independently.

Run directly:
    uvicorn agent_service:app --host 0.0.0.0 --port 8001

Endpoints:
    GET  /health   -> liveness probe for this service itself
    POST /heal     -> {"error_log": "..."} -> triggers diagnose_and_heal()
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent_brain import diagnose_and_heal

app = FastAPI(title="SRE-Agent Brain Service", version="1.0.0")


class HealRequest(BaseModel):
    error_log: str = Field(
        ..., min_length=1, description="Captured log text describing the incident"
    )


class HealResponse(BaseModel):
    report: str


@app.get("/health")
def health():
    return {"status": "OK", "service": "agent-brain"}


@app.post("/heal", response_model=HealResponse)
def heal(payload: HealRequest):
    """
    Accepts a raw error log snippet and runs the full RAG + tool-calling +
    verification loop synchronously, returning the agent's final report.
    """
    try:
        report = diagnose_and_heal(payload.error_log)
    except Exception as e:  # surfaces LLM/tool errors as a clean 500 instead of a crash
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")

    return HealResponse(report=report)
