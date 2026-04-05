FROM docker.elastic.co/logstash/logstash:9.3.1

# Switch to root to install dependencies
USER root

# Try to install Python 3.12 via microdnf
RUN microdnf install -y python3.12 python3.12-pip && \
    microdnf clean all && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python3 && \
    ln -sf /usr/bin/pip3.12 /usr/local/bin/pip3

# Install uv for faster dependency resolution
RUN pip3 install --no-cache-dir uv

# Set work directory
WORKDIR /app

# Copy the entire src directory (includes all modules and package structure)
COPY src/ /app/src/

# Copy dependency files
COPY pyproject.toml uv.lock /app/

# Install dependencies using uv
RUN uv pip install --system --no-cache -r pyproject.toml

# Note: logstashagent.yml is mounted at runtime via docker-compose volumes
# Config is read from /app/logstashui.yml (preferred) or /app/logstashui.example.yml

# Create directories for Logstash configs and pipelines
RUN mkdir -p /etc/logstash \
    /etc/logstash/conf.d \
    /etc/logstash/config \
    /etc/logstash/pipeline-metadata \
    /var/log/logstash \
    /app/src/logstashagent/data/logs \
    /tmp

# Copy Logstash configuration files
COPY docker/config/logstash.yml /etc/logstash/logstash.yml
COPY docker/config/pipelines.yml /etc/logstash/pipelines.yml
COPY docker/config/jvm.options /etc/logstash/jvm.options
COPY docker/config/log4j2.properties /etc/logstash/log4j2.properties

# Copy simulation pipeline configs
COPY docker/config/simulate_start.conf /etc/logstash/config/simulate_start.conf
COPY docker/config/simulate_end.conf /etc/logstash/config/simulate_end.conf

# Set permissions
RUN chown -R logstash:logstash /etc/logstash /var/log/logstash /app /tmp && \
    chmod -R 755 /etc/logstash /var/log/logstash && \
    chmod 1777 /tmp

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    chown logstash:logstash /entrypoint.sh

# Set default LOGSTASH_URL for local development
# Uses host.docker.internal which works cross-platform with extra_hosts in docker-compose
# Can be overridden at build time or runtime
ARG LOGSTASH_URL=http://host.docker.internal:8080
ENV LOGSTASH_URL=${LOGSTASH_URL}
ENV MALLOC_ARENA_MAX=4
ENV PYTHONPATH=/app/src

# Switch back to logstash user
USER logstash

# Expose ports
# 9600: Logstash API
# 9449: Logstash HTTP input (for sample events)
# 9500: FastAPI sidecar API
EXPOSE 9600 9449 9500

# Use custom entrypoint
ENTRYPOINT ["/entrypoint.sh"]
