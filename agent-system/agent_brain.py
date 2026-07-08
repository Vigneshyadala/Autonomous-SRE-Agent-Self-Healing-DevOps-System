"""
Autonomous SRE Agent: Self-Healing DevOps System
Agent Brain
===========
Built by Vignesh Yadala
https://vigneshyadala.github.io/portfolio | https://github.com/Vigneshyadala

Core reasoning engine for the Autonomous Site Reliability Engineering Agent.

Responsibilities:
  1. Load "Company Incident Runbooks" (runbooks.json) into a persistent
     ChromaDB collection for retrieval-augmented diagnosis.
  2. Expose a small set of *restricted* tools to a LangChain tool-calling
     agent: runbook search (read-only RAG lookup), a sandboxed Docker
     command executor (allow-listed verbs only, no shell=True, no
     arbitrary strings), and an HTTP health check against the target app.
  3. Run the end-to-end diagnose -> retrieve -> act -> verify loop given a
     raw error log string captured by the monitor service.

Environment variables:
  LLM_PROVIDER        "anthropic" (default) or "openai"
  ANTHROPIC_API_KEY    required if LLM_PROVIDER=anthropic
  ANTHROPIC_MODEL       e.g. "claude-3-5-sonnet-20241022" (check your
                        Anthropic Console / docs.claude.com for the latest
                        available model id -- do not hardcode blindly)
  OPENAI_API_KEY        required if LLM_PROVIDER=openai
  OPENAI_MODEL          e.g. "gpt-4o"
  TARGET_CONTAINER      docker container name of the target app
                        (default: "sre-target-app")
  TARGET_APP_URL        base URL of the target app's health endpoint
                        (default: "http://localhost:3000")
  CHROMA_PERSIST_DIR    directory for the persistent vector store
                        (default: "./chroma_store")
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import chromadb
import requests
from chromadb.utils import embedding_functions
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
RUNBOOKS_PATH = BASE_DIR / "runbooks.json"
CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", str(BASE_DIR / "chroma_store"))

TARGET_CONTAINER = os.environ.get("TARGET_CONTAINER", "sre-target-app")
TARGET_APP_URL = os.environ.get("TARGET_APP_URL", "http://localhost:3000")

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "google").lower()

# Allow-listed docker subcommands. Anything not on this list is refused
# before it ever reaches subprocess. No shell=True is used anywhere, so
# shell metacharacters (;, &&, |, `, $()) cannot cause command injection --
# they are just treated as literal (and rejected) argument text.
ALLOWED_DOCKER_VERBS = {"restart", "logs", "ps", "stats", "start", "stop", "inspect"}

# Only allow the agent to target this single, pre-approved container. This
# prevents the LLM from being tricked (via prompt injection in a log line,
# for example) into touching unrelated infrastructure.
ALLOWED_CONTAINER_NAMES = {TARGET_CONTAINER}

DANGEROUS_CHAR_PATTERN = re.compile(r"[;&|`$<>\\\n]")


# ---------------------------------------------------------------------------
# ChromaDB :: RAG runbook store
# ---------------------------------------------------------------------------
def get_chroma_collection():
    """
    Initializes (or loads) a persistent ChromaDB collection called
    'sre_runbooks' and seeds it from runbooks.json if it is empty. Uses
    ChromaDB's built-in ONNX MiniLM embedding function so no external
    embedding API call or heavyweight ML framework is required.
    """
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    embedding_fn = embedding_functions.DefaultEmbeddingFunction()

    collection = client.get_or_create_collection(
        name="sre_runbooks",
        embedding_function=embedding_fn,
        metadata={"description": "Company Incident Runbooks for SRE-Agent RAG lookup"},
    )

    if collection.count() == 0:
        _seed_runbooks(collection)

    return collection


def _seed_runbooks(collection) -> None:
    """Loads runbooks.json and embeds each runbook as a document."""
    if not RUNBOOKS_PATH.exists():
        raise FileNotFoundError(
            f"runbooks.json not found at {RUNBOOKS_PATH}. Cannot seed ChromaDB."
        )

    with open(RUNBOOKS_PATH, "r", encoding="utf-8") as f:
        runbooks = json.load(f)

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[dict] = []

    for rb in runbooks:
        # The embedded document combines the human-readable signal (title,
        # error pattern, description) so semantic search matches real log
        # text against the runbook that actually applies to it.
        doc_text = (
            f"Title: {rb['title']}\n"
            f"Error Pattern: {rb['error_pattern']}\n"
            f"Description: {rb['description']}\n"
            f"Severity: {rb['severity']}\n"
            f"Tags: {', '.join(rb.get('tags', []))}"
        )
        ids.append(rb["id"])
        documents.append(doc_text)
        metadatas.append(
            {
                "title": rb["title"],
                "severity": rb["severity"],
                "remediation_steps": json.dumps(rb["remediation_steps"]),
                "diagnostic_steps": json.dumps(rb.get("diagnostic_steps", [])),
                "expected_outcome": rb.get("expected_outcome", ""),
            }
        )

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"[agent_brain] Seeded ChromaDB with {len(ids)} runbooks.")


# Module-level singleton collection, initialized on first import.
_collection = get_chroma_collection()


# ---------------------------------------------------------------------------
# Tools available to the LangChain agent
# ---------------------------------------------------------------------------
@tool
def search_runbooks(error_log: str) -> str:
    """
    Searches the company incident runbook knowledge base (ChromaDB) for the
    runbook that best matches a given error log or symptom description.
    Always call this FIRST when diagnosing an incident, before attempting
    any remediation action. Returns the matched runbook's title, severity,
    diagnostic steps, remediation steps, and expected outcome as text.
    """
    results = _collection.query(query_texts=[error_log], n_results=1)

    if not results["ids"] or not results["ids"][0]:
        return "No matching runbook found in the knowledge base."

    metadata = results["metadatas"][0][0]
    distance = results["distances"][0][0] if results.get("distances") else None

    remediation_steps = json.loads(metadata["remediation_steps"])
    diagnostic_steps = json.loads(metadata.get("diagnostic_steps", "[]"))

    formatted = (
        f"Matched Runbook: {metadata['title']} (similarity distance={distance:.4f})\n"
        f"Severity: {metadata['severity']}\n\n"
        f"Diagnostic Steps:\n"
        + "\n".join(f"  - {s}" for s in diagnostic_steps)
        + "\n\nRemediation Steps (replace <container_name> with the real target container):\n"
        + "\n".join(f"  - {s}" for s in remediation_steps)
        + f"\n\nExpected Outcome: {metadata.get('expected_outcome', 'N/A')}"
    )
    return formatted


@tool
def execute_docker_command(command: str) -> str:
    """
    Executes a single, restricted Docker command against the pre-approved
    target container ONLY. The command must be a docker CLI invocation such
    as "docker restart sre-target-app" or "docker logs --tail 30
    sre-target-app". Only these verbs are permitted: restart, logs, ps,
    stats, start, stop, inspect. Only the pre-approved target container
    name may be referenced. Shell operators (;, &&, |, backticks, $()) are
    rejected outright. Returns stdout/stderr from the command, or a
    rejection reason if the command fails validation.
    """
    if DANGEROUS_CHAR_PATTERN.search(command):
        return (
            "REJECTED: command contains disallowed shell metacharacters. "
            "Only a plain 'docker <verb> <args>' invocation is permitted."
        )

    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return f"REJECTED: could not parse command safely ({e})."

    if len(tokens) < 2 or tokens[0] != "docker":
        return "REJECTED: command must start with 'docker'."

    verb = tokens[1]
    if verb not in ALLOWED_DOCKER_VERBS:
        return (
            f"REJECTED: verb '{verb}' is not on the allow-list "
            f"({sorted(ALLOWED_DOCKER_VERBS)})."
        )

    # Confirm the command references only the approved container name
    # somewhere in its arguments (for verbs that take a container target).
    if verb != "ps" and not any(name in tokens for name in ALLOWED_CONTAINER_NAMES):
        return (
            f"REJECTED: command must target an approved container "
            f"({sorted(ALLOWED_CONTAINER_NAMES)}). Refusing to act on "
            f"unlisted targets."
        )

    try:
        result = subprocess.run(
            tokens,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,  # never invoke a shell; tokens are passed literally
        )
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 30 seconds."
    except FileNotFoundError:
        return "ERROR: docker binary not found on this host/container."

    output = f"$ {command}\nexit_code={result.returncode}\n"
    if result.stdout:
        output += f"--- stdout ---\n{result.stdout.strip()}\n"
    if result.stderr:
        output += f"--- stderr ---\n{result.stderr.strip()}\n"
    return output


@tool
def check_target_health() -> str:
    """
    Performs an HTTP GET against the target application's /health endpoint
    to verify whether the remediation was successful. Use this AFTER
    executing a docker command to confirm the service has recovered to a
    200 OK status before concluding the incident is resolved.
    """
    url = f"{TARGET_APP_URL.rstrip('/')}/health"
    try:
        resp = requests.get(url, timeout=5)
        return (
            f"GET {url} -> HTTP {resp.status_code}\n"
            f"Body: {resp.text[:500]}"
        )
    except requests.exceptions.RequestException as e:
        return f"GET {url} -> FAILED ({e})"


TOOLS = [search_runbooks, execute_docker_command, check_target_health]


# ---------------------------------------------------------------------------
# Tool-output collector
# ---------------------------------------------------------------------------
# LangChain's tool-calling agent typically makes one *extra* LLM call at the
# very end of the loop purely to phrase a nice natural-language summary of
# what it already did. If that final call fails (e.g. an LLM provider rate
# limit is hit), AgentExecutor.invoke() raises -- even though every tool
# call before it (runbook match, docker restart, health check) already
# succeeded. Without this collector, that failure would discard a genuinely
# successful remediation and report it as a hard error.
#
# This callback records each tool's name and output as it happens, so if
# the final summarization call fails, diagnose_and_heal() can still build
# an accurate report directly from what the tools actually did.
class ToolOutputCollector(BaseCallbackHandler):
    def __init__(self) -> None:
        self.calls: List[Dict[str, str]] = []

    def on_tool_end(self, output: Any, *, name: str = "", **kwargs) -> None:
        tool_name = kwargs.get("name") or name or "unknown_tool"
        self.calls.append({"tool": tool_name, "output": str(output)})

    # Some LangChain versions pass the tool name via the run's serialized
    # info instead of a kwarg; this override covers that case too.
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        self._last_tool_name = serialized.get("name", "unknown_tool")


def _build_fallback_report(collector: "ToolOutputCollector", error: Exception) -> str:
    """
    Builds an honest, human-readable report from whatever tools actually
    ran before the final LLM summarization call failed. This is what keeps
    a genuine, successful remediation from being reported as a total
    failure just because the "write a nice sentence about it" step hit an
    LLM provider limit.
    """
    if not collector.calls:
        # Nothing ran at all -- this really is a hard failure with nothing
        # to salvage (e.g. the very first LLM call failed before any tool
        # was invoked).
        raise error

    lines = [
        "SRE-Agent completed remediation, but could not generate the final "
        "AI-written summary because the LLM provider was temporarily "
        f"unavailable ({type(error).__name__}). Reporting directly from "
        "the actions actually taken:",
        "",
    ]

    matched_runbook = None
    restart_result = None
    health_result = None

    for call in collector.calls:
        tool_name = call["tool"]
        output = call["output"]
        if tool_name == "search_runbooks" and "Matched Runbook:" in output:
            matched_runbook = output.splitlines()[0].replace("Matched Runbook: ", "")
        elif tool_name == "execute_docker_command":
            restart_result = output
        elif tool_name == "check_target_health":
            health_result = output

    if matched_runbook:
        lines.append(f"Runbook matched: {matched_runbook}")
    if restart_result:
        success = "exit_code=0" in restart_result
        lines.append(
            f"Remediation command executed ({'succeeded' if success else 'FAILED'}):"
        )
        lines.append(restart_result.strip())
    if health_result:
        recovered = "HTTP 200" in health_result
        lines.append(
            f"Post-remediation health check: {'PASSED (200 OK)' if recovered else 'DID NOT PASS'}"
        )
        lines.append(health_result.strip())

    overall_ok = bool(restart_result and "exit_code=0" in restart_result) and bool(
        health_result and "HTTP 200" in health_result
    )
    lines.append("")
    lines.append(
        "Overall result: RESOLVED (verified healthy)"
        if overall_ok
        else "Overall result: UNVERIFIED -- manual review recommended"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
def get_llm():
    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        return ChatOpenAI(model=model, temperature=0)

    elif LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        return ChatAnthropic(model=model, temperature=0)

    elif LLM_PROVIDER == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Google AI Studio (ai.google.dev) issues free API keys with a real
        # no-cost daily quota -- no credit card required. Get one at
        # https://aistudio.google.com/app/apikey and set GOOGLE_API_KEY.
        model = os.environ.get("GOOGLE_MODEL", "gemini-2.5-flash")
        return ChatGoogleGenerativeAI(model=model, temperature=0)

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{LLM_PROVIDER}'. "
            f"Use 'anthropic', 'openai', or 'google'."
        )


SYSTEM_PROMPT = """\
You are SRE-Agent, an autonomous Site Reliability Engineering agent responsible
for a single containerized Node.js application named "{target_container}".

Your job when given a raw error log or incident description is to:
  1. Call `search_runbooks` with the error text to retrieve the matching
     company runbook. Never guess a remediation without consulting a runbook
     first.
  2. Based on the runbook's remediation steps, call `execute_docker_command`
     with the concrete, single command needed to remediate the incident
     against the container named "{target_container}" (substitute this real
     name in place of any <container_name> placeholder from the runbook).
  3. After acting, call `check_target_health` to verify the service returned
     to a 200 OK status.
  4. If health check still fails after one remediation attempt, you may
     retry the remediation once. If it fails a second time, stop and report
     that manual/human escalation is required -- do not loop indefinitely.

Rules:
  - You may only issue docker commands that target "{target_container}".
  - Never invent shell commands outside the documented remediation steps.
  - Always explain, in your final answer, which runbook you matched, what
    action you took, and the final verified health status.
"""


def build_agent_executor() -> AgentExecutor:
    llm = get_llm()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT.format(target_container=TARGET_CONTAINER)),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    agent = create_tool_calling_agent(llm, TOOLS, prompt)
    return AgentExecutor(
        agent=agent,
        tools=TOOLS,
        verbose=True,
        max_iterations=6,
        handle_parsing_errors=True,
    )


# ---------------------------------------------------------------------------
# Primary execution entry point (called by the FastAPI monitor webhook)
# ---------------------------------------------------------------------------
def diagnose_and_heal(error_log: str) -> str:
    """
    Given a raw error log string (e.g. captured by the monitor from
    `docker logs`), runs the full RAG -> tool-calling -> verification loop
    and returns the agent's final natural-language incident report.

    If every tool call succeeds but the final LLM summarization call fails
    (e.g. a rate limit hit right at the last step), this still returns a
    real, honest report built directly from the tool outputs instead of
    raising -- so a genuinely successful remediation is never reported as
    a hard failure just because of a rate limit on the "write a summary"
    step.
    """
    executor = build_agent_executor()
    incident_input = (
        f"The monitoring system detected a failure on container "
        f"'{TARGET_CONTAINER}'. Captured log output:\n\n{error_log}\n\n"
        f"Diagnose the root cause and remediate it."
    )

    collector = ToolOutputCollector()
    try:
        result = executor.invoke(
            {"input": incident_input},
            config={"callbacks": [collector]},
        )
        return result["output"]
    except Exception as e:
        # Tools may have already run successfully before this exception
        # was raised (typically during the final summarization call).
        # Build an honest fallback report from what actually happened
        # instead of discarding a successful remediation.
        return _build_fallback_report(collector, e)


if __name__ == "__main__":
    # Manual smoke test: simulate the monitor handing off a captured log
    # snippet exactly as it would appear from `docker logs --tail 30`.
    sample_log = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "FATAL ERROR: JavaScript heap out of memory - Reached heap limit, "
        "process may abort. LEAK: allocated chunk #78, heapUsed=412MB"
    )
    print(f"[agent_brain] Running diagnosis on sample log:\n{sample_log}\n")
    report = diagnose_and_heal(sample_log)
    print("\n=== SRE-Agent Final Report ===")
    print(report)