FROM docker.elastic.co/logstash/logstash:9.3.0

# Switch to root to install dependencies
USER root

# Install Python and system dependencies
RUN microdnf install -y python3 python3-pip && \
    microdnf clean all

# Set work directory for FastAPI app
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy FastAPI application
COPY main.py .
COPY slots.py .
COPY logstashagent.yml .

# Create directories for Logstash configs and pipelines
RUN mkdir -p /etc/logstash \
    /etc/logstash/conf.d \
    /etc/logstash/config \
    /etc/logstash/pipeline-metadata \
    /var/log/logstash \
    /tmp

# Copy Logstash configuration files
COPY config/logstash.yml /etc/logstash/logstash.yml
COPY config/pipelines.yml /etc/logstash/pipelines.yml
COPY config/jvm.options /etc/logstash/jvm.options

# Copy simulation pipeline configs
COPY config/simulate_start.conf /etc/logstash/config/simulate_start.conf
COPY config/simulate_end.conf /etc/logstash/config/simulate_end.conf
COPY config/output-block.conf /etc/logstash/config/output-block.conf

# Set permissions
RUN chown -R logstash:logstash /etc/logstash /var/log/logstash /app /tmp && \
    chmod -R 755 /etc/logstash /var/log/logstash && \
    chmod 1777 /tmp

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    chown logstash:logstash /entrypoint.sh

# Switch back to logstash user
USER logstash

# Expose ports
# 9600: Logstash API
# 9449: Logstash HTTP input (for sample events)
# 9500: FastAPI sidecar API
# 8082: HTTP input for simulation pipelines
EXPOSE 9600 9449 9500 8082

# Use custom entrypoint
ENTRYPOINT ["/entrypoint.sh"]
