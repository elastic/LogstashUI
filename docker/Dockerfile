FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    sqlite3 \
  && rm -rf /var/lib/apt/lists/*

COPY ../LogstashUI/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy *this* build context into /app
COPY ../LogstashUI .

# If theme is directly under /app/theme
WORKDIR /app/theme/static_src
RUN rm -rf node_modules && npm install

# Build Tailwind + collectstatic from where manage.py is
WORKDIR /app
RUN python manage.py tailwind build
RUN python manage.py collectstatic --noinput --clear

RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN mkdir -p /app/data && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown appuser:appuser /entrypoint.sh

USER appuser
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn","LogstashUI.wsgi:application","--bind","0.0.0.0:8080","--workers","2","--timeout","60","--access-logfile","-","--error-logfile","-"]
