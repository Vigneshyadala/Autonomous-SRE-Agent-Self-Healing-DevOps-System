# =============================================================================
# SRE-Agent Target App :: Multi-stage Dockerfile
# Stage 1 installs dependencies in a full node image (build tooling available).
# Stage 2 copies only the pruned node_modules + source into a slim runtime
# image, running as a non-root user with a real HEALTHCHECK wired to /health.
# =============================================================================

# ---------- Stage 1: dependencies ----------
FROM node:20-alpine AS deps
WORKDIR /app

COPY package.json package-lock.json* ./
# Use npm ci when a lockfile exists for reproducible installs; fall back to
# npm install on first run when no lockfile has been generated yet.
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

# ---------- Stage 2: runtime ----------
FROM node:20-alpine AS runtime
WORKDIR /app

# Create an unprivileged user to run the app instead of root.
RUN addgroup -S sre && adduser -S sre -G sre

ENV NODE_ENV=production \
    PORT=3000

COPY --from=deps /app/node_modules ./node_modules
COPY package.json ./
COPY app.js ./

# --expose-gc lets the /chaos/reset endpoint force a real garbage collection
# after clearing leaked buffers, so remediation is fully effective.
RUN chown -R sre:sre /app
USER sre

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O- http://localhost:3000/health || exit 1

CMD ["node", "--expose-gc", "app.js"]
