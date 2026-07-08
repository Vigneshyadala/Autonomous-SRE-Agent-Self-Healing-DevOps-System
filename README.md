<div align="center">

<table>
<tr>
<td valign="middle">

```
   ___        __                                              _____ ____  _____
  / _ \      / /_____  ____  ____  ____ ___  ____  __  _______/ ___// __ \/ ___/
 / __ |_    / / ___/ / __ \/ __ \/ __ `__ \/ __ \/ / / / ___/\__ \/ /_/ / __ \
/ /_/ | |  / (__  ) /_/ / / / / / / / / / / /_/ / /_/ (__  )___/ / _, _/ /_/ /
\____/|_| /_/____/\____/_/ /_/_/ /_/ /_/ /_/\____/\__,_/____/____/_/ |_|\____/
```

# 🤖 Autonomous SRE Agent
### Self-healing infrastructure. No human in the loop.

</td>
<td valign="middle" width="40">&nbsp;&nbsp;&nbsp;</td>
<td valign="middle">

<img src="./assets/vy-brand-lockup.svg" alt="Engineered end-to-end by Vignesh Yadala" width="280"/>

</td>
</tr>
</table>

![Status](https://img.shields.io/badge/status-live%20demo-2dd4bf?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-0.2.16-1C3C3C?style=flat-square)
![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-ff3b5c?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-ffb088?style=flat-square)

[**🚀 Live Interactive Demo**](https://vigneshyadala.github.io/Autonomous-SRE-Agent-Self-Healing-DevOps-System/) · [Portfolio](https://vigneshyadala.github.io/portfolio) · [GitHub](https://github.com/Vigneshyadala)

</div>

---

## 📌 About

An agentic AI system that watches a live containerized application, diagnoses
production incidents against a retrieval-augmented "company runbook" knowledge
base, and **autonomously executes the fix** — no dashboard-refreshing, no
2 AM pages, no human touching the keyboard.

It's the full production loop, compressed into three Docker containers:

```
Detect  →  Diagnose (RAG)  →  Decide (LLM tool-calling)  →  Heal (Docker)  →  Verify
```

Every incident it resolves is timestamped, logged, and auditable — nothing
is staged. The included live demo bundles a **real verified incident**
straight from the system's own `/incidents` record, alongside an
interactive simulation you can replay yourself.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 **RAG Runbook Matching** | ChromaDB vector search over a real "company runbook" library — the agent reasons from institutional knowledge, not guesswork |
| 🛠️ **Tool-Calling Remediation** | LangChain agent decides *when* and *which* fix to apply, restricted to an allow-listed Docker toolset |
| 📡 **Autonomous Monitoring** | FastAPI watcher polls `/health` every 10s, captures logs the instant something degrades |
| 🔒 **Sandboxed Execution** | No raw shell access — only 7 whitelisted Docker verbs, one pre-approved target container, zero shell metacharacters |
| ✅ **Self-Verifying** | The agent doesn't just act — it re-checks `/health` afterward and reports the real outcome |
| 🔥 **Chaos Engineering Built-In** | Memory leaks, DB connection failures, and CPU spikes on tap via dedicated endpoints |
| 🔌 **Multi-LLM Ready** | Swap between Gemini, OpenAI, and Claude via a single env var — no code changes |
| 📊 **Full Audit Trail** | Every detection, diagnosis, and resolution logged with timestamps via `/incidents` |

---

## 🛠️ Tech Stack

![Node.js](https://img.shields.io/badge/Node.js-18+-339933?style=flat-square&logo=node.js&logoColor=white)
![Express](https://img.shields.io/badge/Express-4.19-000000?style=flat-square&logo=express&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-agent-1C3C3C?style=flat-square)
![ChromaDB](https://img.shields.io/badge/ChromaDB-vector%20store-ff3b5c?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)

- **Target application** — Node.js / Express, with intentional chaos-injection endpoints
- **Monitor & webhook** — Python / FastAPI, polling + incident capture
- **Agent brain** — LangChain tool-calling agent + ChromaDB RAG over runbooks.json
- **Orchestration** — Docker Compose, all three services networked together
- **LLM providers** — Gemini 2.5 Flash / GPT-4.1 mini / Claude Sonnet, hot-swappable

---

## 🏗️ Architecture

```
                    ┌─────────────────────┐
                    │   1. target-app       │   Node.js + Express
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

| Service | Tech | Port | Role |
|---|---|---|---|
| `target-app` | Node.js / Express | `3500 → 3000` | App-under-test with chaos endpoints |
| `monitor-webhook` | Python / FastAPI | `8000` | Health polling, incident detection, log capture |
| `agent-brain` | Python / LangChain / ChromaDB | `8001` | RAG diagnosis + restricted tool-calling remediation |

---

## 🚀 Quick Start

**1️⃣ Clone the repo**
```bash
git clone https://github.com/Vigneshyadala/Autonomous-SRE-Agent-Self-Healing-DevOps-System.git
cd Autonomous-SRE-Agent-Self-Healing-DevOps-System
```

**2️⃣ Configure your LLM credentials**
```bash
cp agent-system/.env.example agent-system/.env
# edit agent-system/.env → set LLM_PROVIDER + the matching API key
```

**3️⃣ Build and start the whole stack**
```bash
docker compose up --build
```

**4️⃣ Confirm baseline health**
```bash
curl http://localhost:3500/health
```

**5️⃣ Trigger a real incident**
```bash
curl http://localhost:3500/chaos/leak    # simulated memory leak
curl http://localhost:3500/chaos/db      # simulated DB connection failure
curl http://localhost:3500/chaos/cpu     # simulated CPU spike
```

**6️⃣ Watch it heal itself**
```bash
curl http://localhost:8000/status
curl http://localhost:8000/incidents
```

Within 1–2 polling cycles (10–20s), the monitor detects the degraded
`/health` response, captures the container's logs, hands them to
`agent-brain`, which matches the correct runbook in ChromaDB, issues a
`docker restart`, and confirms recovery — all without a human touching
the keyboard.

---

## 🔒 Security & Safety Design

The agent is deliberately **not** given a raw shell:

✅ `execute_docker_command` is an allow-listed tool — only 7 verbs permitted (`restart`, `logs`, `ps`, `stats`, `start`, `stop`, `inspect`)
✅ Only the one pre-approved target container may ever be referenced
✅ Shell metacharacters are rejected outright
✅ Every command runs via `subprocess` with `shell=False` — never through a shell interpreter
✅ The LLM decides *when* and *which* runbook action to take, but cannot escalate beyond this fixed, auditable toolset

This is what makes the "autonomous" part safe enough to demo live.

---

## 📁 Repository Structure

```
Autonomous-SRE-Agent-Self-Healing-DevOps-System/
├── target-app/            # Node.js Express app + chaos endpoints
│   ├── app.js
│   ├── Dockerfile
│   └── package.json
├── agent-system/          # LangChain agent brain + ChromaDB RAG
│   ├── agent_brain.py
│   ├── agent_service.py
│   ├── runbooks.json
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── monitor-webhook/       # FastAPI monitor + webhook trigger
│   ├── monitor.py
│   ├── requirements.txt
│   └── Dockerfile
├── assets/                # Brand assets (logo, wordmark)
│   ├── vy-brand-lockup.svg
│   └── vy-brand-stacked.svg
├── index.html             # Live interactive demo + verified real incident
└── docker-compose.yml
```

---

## 📸 Live Demo

🌐 **Try it live →** [Autonomous SRE Agent demo](https://vigneshyadala.github.io/Autonomous-SRE-Agent-Self-Healing-DevOps-System/)

The demo page includes a **Verified Real Test Run** card — real timestamps,
real captured logs, real agent remediation — plus an interactive simulation
you can trigger yourself.

---

## 👨‍💻 Developer

<div align="center">

<img src="./assets/vy-brand-stacked.svg" alt="Engineered end-to-end by Vignesh Yadala" width="320"/>

| Name | Role | GitHub |
|---|---|---|
| Vignesh Yadala | Designer & Developer | [@Vigneshyadala](https://github.com/Vigneshyadala) |

🤖 **Autonomous SRE Agent** — All Rights Reserved © Vignesh Yadala 2026

Built with LangChain, ChromaDB, FastAPI & Docker

</div>
