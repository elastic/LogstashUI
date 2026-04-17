#!/bin/bash
set -e

# Change to Django project directory
cd /app/src/logstashui

# Create data directory if it doesn't exist
mkdir -p /app/data

# Diagnostic: Check data directory permissions and contents
echo "=========================================="
echo "Database Directory Diagnostics"
echo "=========================================="
echo "Directory permissions:"
ls -lah /app/ | grep data
echo ""
echo "Directory contents:"
ls -lah /app/data/
echo ""
echo "Current user: $(whoami)"
echo "User ID: $(id)"
echo ""

# Check if database file exists and is readable
if [ -f /app/data/db.sqlite3 ]; then
    echo "Database file exists ($(stat -c%s /app/data/db.sqlite3) bytes)"
    if [ -r /app/data/db.sqlite3 ]; then
        echo "Database file is readable"
    else
        echo "WARNING: Database file exists but is NOT readable!"
    fi
    if [ -w /app/data/db.sqlite3 ]; then
        echo "Database file is writable"
    else
        echo "WARNING: Database file exists but is NOT writable!"
    fi
    
    # Check if migrations table exists
    echo ""
    echo "Checking for existing migrations table..."
    if sqlite3 /app/data/db.sqlite3 "SELECT COUNT(*) FROM django_migrations;" 2>/dev/null; then
        MIGRATION_COUNT=$(sqlite3 /app/data/db.sqlite3 "SELECT COUNT(*) FROM django_migrations;" 2>/dev/null)
        echo "Found django_migrations table with $MIGRATION_COUNT entries"
    else
        echo "No django_migrations table found (fresh database)"
    fi
else
    echo "Database file does not exist - will be created"
fi
echo "=========================================="
echo ""

# Show what migrations Django thinks need to be applied
echo "Checking migration status..."
python manage.py showmigrations
echo ""

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

exec "$@"
# Start the application with suppressed startup messages
# Redirect Django's startup output to /dev/null but keep error output
#exec "$@" 2>&1 | grep -v "Starting development server" | grep -v "Quit the server" | grep -v "http://0.0.0.0:8080"
