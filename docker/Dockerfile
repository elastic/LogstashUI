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
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md CHANGELOG.md LICENSE.txt NOTICE.txt /app/
COPY src/ /app/src/
COPY docs/ /app/docs/

# Compile Tailwind into theme/static before the wheel is installed.
WORKDIR /app/src/logstashui/theme/static_src
RUN rm -rf node_modules && npm install && npm run build

WORKDIR /app
RUN uv pip install --system --no-cache /app

<<<<<<< HEAD
# Pinned uid so K8s runAsUser/fsGroup is stable. Entrypoint starts as root,
# chowns only LOGSTASHUI_DATA_DIR when needed, then drops to this user (or PUID).
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -m -d /home/appuser appuser
=======
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser
>>>>>>> 67fe80c (Packaging works now!)
RUN mkdir -p /var/lib/logstashui && \
    chown -R appuser:appuser /app /home/appuser /var/lib/logstashui && \
    chmod -R 755 /app

<<<<<<< HEAD
# Copy entrypoint script (must be root so it can chown the bind-mount)
=======
>>>>>>> 67fe80c (Packaging works now!)
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

<<<<<<< HEAD
=======
USER appuser
WORKDIR /var/lib/logstashui
>>>>>>> 67fe80c (Packaging works now!)
EXPOSE 8443
ENTRYPOINT ["/entrypoint.sh"]
CMD ["logstashui", "serve"]
