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

REM Check if logstashui.yml exists
if not exist "logstashui.yml" (
    echo ERROR: logstashui.yml not found!
    echo Please run this script from the bin directory or ensure the file exists.
    exit /b 1
)

REM Now enable delayed expansion for variable parsing
setlocal enabledelayedexpansion

REM Detect mode from logstashui.yml
echo Detecting simulation mode
for /f "tokens=2" %%a in ('findstr /C:"simulation_mode:" logstashui.yml') do set MODE=%%a

echo Detected mode: !MODE!
echo.

if /i "!MODE!"=="host" (
    echo ========================================
    echo HOST MODE SHUTDOWN
    echo ========================================
    echo Stopping native LogstashAgent process
    
    REM Kill Python processes listening on port 9501 (uvicorn)
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :9501 ^| findstr LISTENING') do (
        echo Killing process on port 9501 (PID: %%a)
        taskkill /PID %%a /F >nul 2>&1
    )
    
    REM Also kill the LogstashAgent window if it exists
    taskkill /FI "WINDOWTITLE eq LogstashAgent*" /F >nul 2>&1
    
    echo LogstashAgent stopped
    
    echo.
    echo Stopping Docker containers (UI + Nginx)
    %DOCKER_COMPOSE% down
    
    REM Force remove agent container if it exists
    echo Removing any stray agent containers
    docker rm -f logstashui-logstashagent-1 2>nul
    
) else (
    echo ========================================
    echo EMBEDDED MODE SHUTDOWN
    echo ========================================
    echo Stopping all containers
    %DOCKER_COMPOSE% down
)

echo.
echo ========================================
echo LogstashUI Stopped Successfully
echo ========================================
echo.

REM Restore original directory
popd
