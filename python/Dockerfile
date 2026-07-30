# ─── Build Stage ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create build directory
WORKDIR /build

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/
COPY README.md .

# Install the package and dependencies into a target directory
RUN pip install --no-cache-dir --target=/install .

# ─── Runtime Stage ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r riven && useradd -r -g riven -m -d /home/riven -s /bin/bash riven

# Copy installed packages from builder
COPY --from=builder /install /usr/local/lib/python3.12/site-packages

# Copy application source
COPY --from=builder /build/src /app/src
COPY --from=builder /build/pyproject.toml /app/pyproject.toml

# Create audit log directory
RUN mkdir -p /var/log/riven-mcp && chown riven:riven /var/log/riven-mcp

WORKDIR /app

# Create empty .env file so pydantic-settings can read it without PermissionError
RUN touch /app/.env && chown riven:riven /app/.env

# Set environment defaults (can be overridden at runtime)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    MCP_TRANSPORT=stdio \
    LOG_JSON=true \
    LOG_LEVEL=INFO

# Health check (only meaningful in HTTP mode)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:${MCP_PORT:-8080}/health || exit 0

# Switch to non-root user
USER riven

# Expose HTTP port (only used in http transport mode)
EXPOSE 8080

# Default entry point — can be overridden in docker-compose
ENTRYPOINT ["python", "-m", "riven_mcp.server"]
