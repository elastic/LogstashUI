@echo off
setlocal
cd /d "%~dp0\.."
where docker >nul 2>&1
if errorlevel 1 (
  echo ERROR: Docker is required for bin\test_databases.bat
  exit /b 1
)
uv sync --extra databases --group dev
uv run pytest src\logstashui --no-cov
if errorlevel 1 exit /b 1
docker compose -f docker\docker-compose.db.yml up -d --wait
if errorlevel 1 exit /b 1

set LOGSTASHUI_DB_ENGINE=postgresql
set LOGSTASHUI_DB_HOST=127.0.0.1
set LOGSTASHUI_DB_PORT=55432
set LOGSTASHUI_DB_NAME=logstashui
set LOGSTASHUI_DB_USER=logstashui
set LOGSTASHUI_DB_PASSWORD=logstashui
uv run pytest src\logstashui --no-cov
if errorlevel 1 goto :down

set LOGSTASHUI_DB_ENGINE=mysql
set LOGSTASHUI_DB_PORT=53306
set LOGSTASHUI_DB_USER=root
uv run pytest src\logstashui --no-cov
if errorlevel 1 goto :down

set LOGSTASHUI_DB_PORT=53307
uv run pytest src\logstashui --no-cov
if errorlevel 1 goto :down

set LOGSTASHUI_LIVE_DB=1
set LOGSTASHUI_LIVE_PG_PORT=55432
set LOGSTASHUI_LIVE_MARIA_PORT=53306
set LOGSTASHUI_LIVE_MYSQL_PORT=53307
uv run pytest src\logstashui\LogstashUI\tests\test_migrate_live.py -v --no-cov

:down
if /I not "%1"=="--keep" docker compose -f docker\docker-compose.db.yml down -v
