#!/bin/bash
set -e

# Create data directory if it doesn't exist
mkdir -p /app/LogstashUI/data

# Run migrations
python manage.py makemigrations
python manage.py migrate --noinput

# Start the application
exec "$@"
