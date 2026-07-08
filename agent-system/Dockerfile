# =============================================================================
# SRE-Agent :: Agent Brain Service Dockerfile
# -----------------------------------------------------------------------------
# Autonomous SRE Agent: Self-Healing DevOps System
# Built by Vignesh Yadala
#
# This image bundles the LangChain agent + ChromaDB RAG store AND the Docker
# CLI itself, following the "Docker-outside-of-Docker" pattern: the container
# does not run its own nested Docker daemon, it talks to the HOST daemon via
# a mounted /var/run/docker.sock (wired up in docker-compose.yml). That socket
# mount is what lets execute_docker_command() in agent_brain.py issue real
# `docker restart`, `docker logs`, etc. against sibling containers.
#
# The Docker CLI binary is copied directly from Docker's own official CLI
# image rather than installed via apt-get. This is more reliable across
# Debian releases (docker.io's postinst/package layout has proven
# inconsistent) and meaningfully faster since it skips ~35 apt dependencies.
# =============================================================================

FROM docker:27-cli AS dockercli

FROM python:3.11-slim

WORKDIR /app

# Pull just the docker client binary from the official image above.
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_brain.py .
COPY agent_service.py .
COPY runbooks.json .

# NOTE: this container intentionally runs as root (default). It needs write
# access to the mounted /var/run/docker.sock to issue docker commands, and
# the socket's group ownership/GID varies unpredictably across host
# machines (Docker Desktop, native Linux, WSL2, etc). For a local portfolio
# demo, running as root keeps setup friction-free. For a production
# deployment, replace this with a non-root user whose GID is passed in at
# build time to match the host's docker group (e.g. via --build-arg
# DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)).

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -sf http://localhost:8001/health || exit 1

CMD ["uvicorn", "agent_service:app", "--host", "0.0.0.0", "--port", "8001"]
