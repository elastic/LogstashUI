FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    sqlite3 \
  && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock /app/

# Install Python dependencies
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy the entire src directory
COPY src/ /app/src/

# Copy documentation and changelog
COPY docs/ /app/docs/
COPY CHANGELOG.md /app/CHANGELOG.md

# Set PYTHONPATH so Django can find LogstashUI module
ENV PYTHONPATH=/app/src/logstashui
ENV LOGSTASHUI_DATA_DIR=/var/lib/logstashui

# Build Tailwind CSS
WORKDIR /app/src/logstashui/theme/static_src
RUN rm -rf node_modules && npm install

# Build Tailwind and collect static files
WORKDIR /app/src/logstashui
RUN python manage.py tailwind build
RUN python manage.py collectstatic --noinput --clear

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
# Cert paths are injected by entrypoint from LOGSTASHUI_DATA_DIR (JSON CMD cannot expand env).
CMD ["gunicorn","LogstashUI.wsgi:application","--bind","0.0.0.0:8443","--workers","2","--worker-class","gevent","--worker-connections","1000","--timeout","60","--access-logfile","-","--error-logfile","-"]
