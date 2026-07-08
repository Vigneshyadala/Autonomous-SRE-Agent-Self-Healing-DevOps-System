```
   ___        __                                              _____ ____  _____
  / _ \      / /_____  ____  ____  ____ ___  ____  __  _______/ ___// __ \/ ___/
 / __ |_    / / ___/ / __ \/ __ \/ __ `__ \/ __ \/ / / / ___/\__ \/ /_/ / __ \
/ /_/ | |  / (__  ) /_/ / / / / / / / / / / /_/ / /_/ (__  )___/ / _, _/ /_/ /
\____/|_| /_/____/\____/_/ /_/_/ /_/ /_/ /_/\____/\__,_/____/____/_/ |_|\____/
```

# Autonomous SRE Agent: Self-Healing DevOps System

An agentic AI system that watches a live containerized application, diagnoses
production incidents against a retrieval-augmented "company runbook" knowledge
base, and autonomously executes the fix — no human in the loop.

**Detect → Diagnose (RAG) → Decide (LLM tool-calling) → Heal (Docker) → Verify**

---

### 🧠 Built by **Vignesh Yadala**

> Portfolio: [vigneshyadala.github.io/portfolio](https://vigneshyadala.github.io/portfolio)
> GitHub: [github.com/Vigneshyadala](https://github.com/Vigneshyadala)

This project was designed and engineered end-to-end by Vignesh Yadala as a
demonstration of applied Agentic AI (LangChain/LangGraph), Retrieval-Augmented
Generation, and container-native DevOps automation — combining three
disciplines that rarely meet in a single B.Tech CSE portfolio piece.

---

## Architecture

```
                    ┌─────────────────────┐
                    │   1. target-app      │   Node.js + Express
                    │   /health  /data      │   intentional chaos
                    │   /chaos/leak  /db    │   endpoints
                    └──────────┬───────────┘
                               │ polls every 10s
                               ▼
                    ┌─────────────────────┐
                    │   2. monitor-webhook  │   FastAPI
                    │   detects 5xx/timeout │   captures docker logs
                    └──────────┬───────────┘
                               │ POST /heal { error_log }
                               ▼
                    ┌─────────────────────┐
                    │   3. agent-brain      │   LangChain + ChromaDB
                    │   RAG runbook lookup  │   restricted docker tool
                    │   tool-calling agent  │   health verification
                    └──────────┬───────────┘
                               │ docker restart / logs / exec
                               ▼
                    ┌─────────────────────┐
                    │   back to target-app  │   (self-healed)
                    └─────────────────────┘
```

## Services

| Service | Tech | Port | Role |
|---|---|---|---|
| `target-app` | Node.js / Express | 3500 (host) → 3000 (container) | App-under-test with chaos endpoints |
| `monitor-webhook` | Python / FastAPI | 8000 | Health polling, incident detection, log capture |
| `agent-brain` | Python / LangChain / ChromaDB | 8001 | RAG diagnosis + restricted tool-calling remediation |

## Quick Start

```bash
git clone <this-repo>
cd sre-agent

# 1. Configure your LLM credentials
cp agent-system/.env.example agent-system/.env
# edit agent-system/.env and set LLM_PROVIDER + the matching API key

# 2. Build and start the whole stack
docker compose up --build
```

Once all three containers report healthy:

```bash
# Confirm baseline health
curl http://localhost:3500/health

# Trigger an incident: simulate a memory leak
curl http://localhost:3500/chaos/leak

# Watch the monitor detect it and the agent heal it
curl http://localhost:8000/status
curl http://localhost:8000/incidents
```

Within ~1-2 polling cycles (10-20 seconds), the monitor should detect the
degraded `/health` response, capture the container's logs, hand them to
`agent-brain`, which matches the memory-leak runbook in ChromaDB, issues a
`docker restart sre-target-app`, and confirms recovery — all without a human
touching the keyboard.

Try the other chaos scenarios the same way:

```bash
curl http://localhost:3500/chaos/db     # simulated DB connection failure
curl http://localhost:3500/chaos/cpu    # simulated CPU spike / blocked event loop
```

## Repository Layout

```
sre-agent/
├── target-app/          # Node.js Express app + chaos endpoints
│   ├── app.js
│   ├── Dockerfile
│   └── package.json
├── agent-system/         # LangChain agent brain + ChromaDB RAG
│   ├── agent_brain.py
│   ├── agent_service.py
│   ├── runbooks.json
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── monitor-webhook/      # FastAPI monitor + webhook trigger
│   ├── monitor.py
│   ├── requirements.txt
│   └── Dockerfile
└── docker-compose.yml
```

## Safety Design

The agent is deliberately **not** given a raw shell. `execute_docker_command`
is an allow-listed tool: only a fixed set of Docker verbs are permitted
(`restart`, `logs`, `ps`, `stats`, `start`, `stop`, `inspect`), only the one
pre-approved target container may be referenced, shell metacharacters are
rejected outright, and every command runs via `subprocess` with `shell=False`
— never through a shell interpreter. This is what makes the "autonomous"
part safe enough to demo live: the LLM decides *when* and *which* runbook
action to take, but it cannot escalate beyond that fixed, auditable toolset.

---

*Autonomous SRE Agent: Self-Healing DevOps System — designed, built, and
documented by Vignesh Yadala.*
