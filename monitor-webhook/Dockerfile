# =============================================================================
# Autonomous SRE Agent: Self-Healing DevOps System
# Monitor & Webhook Service Dockerfile
# Built by Vignesh Yadala
# -----------------------------------------------------------------------------
# Needs the Docker CLI (not a daemon) so it can run `docker logs --tail 30`
# against the target-app container directly, using the host socket mounted
# in docker-compose.yml. The CLI binary is copied from Docker's own official
# CLI image rather than installed via apt-get docker.io, which proved
# unreliable (binary sometimes missing after install despite the package
# reporting success).
# =============================================================================

FROM docker:27-cli AS dockercli

FROM python:3.11-slim

WORKDIR /app

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py .

# Runs as root for the same reason as the agent-brain service: friction-free
# access to the mounted /var/run/docker.sock for `docker logs`. See the note
# in agent-system/Dockerfile for the production-hardening approach.

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -sf http://localhost:8000/health || exit 1

CMD ["uvicorn", "monitor:app", "--host", "0.0.0.0", "--port", "8000"]
