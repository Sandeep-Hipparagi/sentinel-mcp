# ==========================================
# Build Stage
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip build hatchling

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Build wheel
RUN python -m build --wheel --no-isolation

# ==========================================
# Runtime Stage
# ==========================================
FROM python:3.12-slim AS runner

WORKDIR /app

# Create non-root user
RUN groupadd -r sentinelmcp && useradd -r -g sentinelmcp -d /app -s /sbin/nologin sentinelmcp && \
    chown -R sentinelmcp:sentinelmcp /app

# Copy wheel from builder and install
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Switch to non-root user
USER sentinelmcp

# OCI labels for GitHub Packages repository linking
LABEL org.opencontainers.image.source="https://github.com/Sandeep-Hipparagi/sentinel-mcp" \
      org.opencontainers.image.description="Registry-ready MCP server: deterministic claim verification, declarative policy gate, Merkle-chained WORM audit ledger, and graph memory with SQLite fallback" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="Sentinel MCP" \
      org.opencontainers.image.version="0.1.1"

ENTRYPOINT ["sentinel-mcp"]
CMD ["--help"]