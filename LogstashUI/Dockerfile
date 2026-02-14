FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY .. .

# Install Tailwind dependencies (need fresh install for Linux)
WORKDIR /app/LogstashUI/theme/static_src
RUN rm -rf node_modules && npm install

# Build Tailwind CSS
WORKDIR /app/LogstashUI
RUN python manage.py tailwind build

# Collect static files
RUN python manage.py collectstatic --noinput

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Create data directory and set permissions
RUN mkdir -p /app/LogstashUI/data && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    chown appuser:appuser /entrypoint.sh

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Run the application
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8080"]
