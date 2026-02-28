#!/bin/bash
set -e

# Create data directory if it doesn't exist
mkdir -p /app/LogstashUI/data

# Run migrations
python manage.py migrate --noinput

# Display welcome message
echo ""
echo "=========================================="
echo "  Welcome to LogstashUI!"
echo "=========================================="
echo ""
echo "To get started, please visit:"
echo "  https://<your-server-ip-or-hostname>"
echo ""
echo "Replace <your-server-ip-or-hostname> with:"
echo "  - localhost (if accessing locally)"
echo "  - Your server's IP address"
echo "  - Your server's hostname/domain"
echo ""
echo "=========================================="
echo ""

# Start the application with suppressed startup messages
# Redirect Django's startup output to /dev/null but keep error output
exec "$@" 2>&1 | grep -v "Starting development server" | grep -v "Quit the server" | grep -v "http://0.0.0.0:8080"
