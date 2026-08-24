@echo off
REM Disable delayed expansion initially to handle paths with exclamation marks
setlocal disabledelayedexpansion

REM ========================================
REM LogstashUI Shutdown Script
REM ========================================

REM Detect docker-compose command (hyphen vs space)
docker-compose version >nul 2>&1
if %errorlevel% equ 0 (
    set DOCKER_COMPOSE=docker-compose
) else (
    docker compose version >nul 2>&1
    if %errorlevel% equ 0 (
        set DOCKER_COMPOSE=docker compose
    ) else (
        echo ERROR: Neither 'docker-compose' nor 'docker compose' found!
        echo Please install Docker Desktop or Docker Compose.
        exit /b 1
    )
)

echo.
echo ========================================
echo LogstashUI Shutdown
echo ========================================
echo.

REM Save current directory and change to project root
pushd "%~dp0.."

setlocal enabledelayedexpansion

echo Stopping native LogstashAgent if port 9501 is in use
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :9501 ^| findstr LISTENING') do (
    echo Killing process on port 9501 (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)
taskkill /FI "WINDOWTITLE eq LogstashAgent*" /F >nul 2>&1

echo Stopping Docker containers
docker rm -f logstashui-logstashagent-1 2>nul
cd docker
%DOCKER_COMPOSE% --profile embedded down --remove-orphans
cd ..

echo.
echo ========================================
echo LogstashUI Stopped Successfully
echo ========================================
echo.

REM Restore original directory
popd
