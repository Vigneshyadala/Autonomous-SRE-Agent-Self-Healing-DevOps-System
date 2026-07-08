"""
Autonomous SRE Agent: Self-Healing DevOps System
Monitor & Webhook Service
=========================
Built by Vignesh Yadala

Simulates a production monitoring tool (think: a lightweight Prometheus/
Blackbox-exporter style watcher). Every POLL_INTERVAL_SECONDS it hits the
target app's /health endpoint. When it detects a failure -- a 5xx status
code OR a request timeout -- it:

  1. Pulls the last N lines of the target container's Docker logs directly
     (this service also has the Docker CLI + socket mounted).
  2. POSTs that log snippet to the Agent Brain service's /heal endpoint.
  3. Records the incident (detection time, resolution time, agent report)
     in an in-memory incident log exposed via GET /incidents.

A simple "incident in progress" guard prevents re-triggering the agent on
every single 10-second tick while an outage is still being handled -- the
monitor waits for /health to recover before arming itself to fire again.
"""

import asyncio
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
import os

TARGET_APP_URL = os.environ.get("TARGET_APP_URL", "http://target-app:3000")
TARGET_CONTAINER = os.environ.get("TARGET_CONTAINER", "sre-target-app")
AGENT_SERVICE_URL = os.environ.get("AGENT_SERVICE_URL", "http://agent-brain:8001")
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "10"))
HEALTH_TIMEOUT_SECONDS = float(os.environ.get("HEALTH_TIMEOUT_SECONDS", "5"))
LOG_TAIL_LINES = int(os.environ.get("LOG_TAIL_LINES", "30"))


# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
class Incident(BaseModel):
    detected_at: str
    trigger: str
    captured_logs: str
    agent_report: Optional[str] = None
    resolved_at: Optional[str] = None
    status: str  # "IN_PROGRESS" | "RESOLVED" | "AGENT_ERROR"


class MonitorState:
    def __init__(self) -> None:
        self.incident_in_progress: bool = False
        self.incidents: List[Incident] = []
        self.last_check_at: Optional[str] = None
        self.last_status: Optional[str] = None
        self.checks_run: int = 0


state = MonitorState()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fetch_container_logs(tail: int = LOG_TAIL_LINES) -> str:
    """Pulls the last `tail` lines from the target container's docker logs."""
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(tail), TARGET_CONTAINER],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        return combined.strip() or "(no log output captured)"
    except Exception as e:
        return f"(failed to capture logs: {e})"


async def check_target_health(client: httpx.AsyncClient) -> tuple[bool, str]:
    """
    Returns (is_healthy, trigger_reason). is_healthy=True means 200 OK.
    Any non-2xx status or a timeout/connection error counts as a failure.
    """
    try:
        resp = await client.get(
            f"{TARGET_APP_URL.rstrip('/')}/health", timeout=HEALTH_TIMEOUT_SECONDS
        )
        if resp.status_code == 200:
            return True, "healthy"
        return False, f"http_{resp.status_code}"
    except httpx.TimeoutException:
        return False, "timeout"
    except httpx.ConnectError:
        return False, "connection_refused"
    except httpx.RequestError as e:
        return False, f"request_error:{e}"


async def trigger_agent(captured_logs: str) -> str:
    """POSTs the captured logs to the Agent Brain service and returns its report."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{AGENT_SERVICE_URL.rstrip('/')}/heal",
            json={"error_log": captured_logs},
        )
        resp.raise_for_status()
        return resp.json()["report"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Background polling loop
# ---------------------------------------------------------------------------
async def polling_loop():
    async with httpx.AsyncClient() as client:
        while True:
            is_healthy, trigger = await check_target_health(client)
            state.last_check_at = now_iso()
            state.last_status = "healthy" if is_healthy else f"unhealthy ({trigger})"
            state.checks_run += 1

            if is_healthy:
                # Recovery: close out any open incident.
                if state.incident_in_progress:
                    print(f"[monitor] Target recovered. Resolving open incident.")
                    open_incidents = [i for i in state.incidents if i.status == "IN_PROGRESS"]
                    if open_incidents:
                        open_incidents[-1].status = "RESOLVED"
                        open_incidents[-1].resolved_at = now_iso()
                    state.incident_in_progress = False

            else:
                if not state.incident_in_progress:
                    # New incident detected -- arm the guard immediately so we
                    # don't fire the agent again on the next tick while it's
                    # still working.
                    state.incident_in_progress = True
                    print(f"[monitor] Incident detected: {trigger}. Capturing logs...")

                    captured_logs = fetch_container_logs()
                    incident = Incident(
                        detected_at=now_iso(),
                        trigger=trigger,
                        captured_logs=captured_logs,
                        status="IN_PROGRESS",
                    )
                    state.incidents.append(incident)

                    print("[monitor] Invoking SRE-Agent brain...")
                    try:
                        report = await trigger_agent(captured_logs)
                        incident.agent_report = report
                        print(f"[monitor] Agent report received:\n{report}")
                    except Exception as e:
                        incident.status = "AGENT_ERROR"
                        incident.agent_report = f"Agent invocation failed: {e}"
                        print(f"[monitor] ERROR invoking agent: {e}")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(polling_loop())
    print(
        f"[monitor] Started. Polling {TARGET_APP_URL}/health every "
        f"{POLL_INTERVAL_SECONDS}s, watching container '{TARGET_CONTAINER}'."
    )
    yield
    task.cancel()


app = FastAPI(
    title="SRE-Agent Monitor & Webhook",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/status")
def status():
    return {
        "monitor_status": "running",
        "target_app_url": TARGET_APP_URL,
        "target_container": TARGET_CONTAINER,
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
        "checks_run": state.checks_run,
        "last_check_at": state.last_check_at,
        "last_status": state.last_status,
        "incident_in_progress": state.incident_in_progress,
        "total_incidents": len(state.incidents),
    }


@app.get("/incidents", response_model=List[Incident])
def incidents():
    return state.incidents


@app.get("/health")
def health():
    # This is the monitor's OWN health, not the target app's.
    return {"status": "OK", "service": "monitor-webhook"}
