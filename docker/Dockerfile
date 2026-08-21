FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LOGSTASHUI_DATA_DIR=/var/lib/logstashui
ENV LOGSTASHUI_DOCS_DIR=/app/docs
ENV DEBUG=False

WORKDIR /app

RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    sqlite3 \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md CHANGELOG.md LICENSE.txt NOTICE.txt /app/
COPY src/ /app/src/
COPY docs/ /app/docs/

# Compile Tailwind, then drop node_modules so the wheel force-include of theme/
# cannot pack them (Hatch force-include bypasses excludes).
WORKDIR /app/src/logstashui/theme/static_src
RUN rm -rf node_modules && npm install && npm run build && rm -rf node_modules

WORKDIR /app
RUN uv pip install --system --no-cache /app

# Pinned uid so K8s runAsUser/fsGroup is stable. Entrypoint starts as root,
# chowns only LOGSTASHUI_DATA_DIR when needed, then drops to this user (or PUID).
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -m -d /home/appuser appuser
RUN mkdir -p /var/lib/logstashui && \
    chown -R appuser:appuser /app /home/appuser /var/lib/logstashui && \
    chmod -R 755 /app

# Copy entrypoint script (must be root so it can chown the bind-mount)
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8443
ENTRYPOINT ["/entrypoint.sh"]
CMD ["logstashui", "serve"]
