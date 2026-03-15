@echo off
REM LogstashUI Startup Script
REM Detects mode from LogstashAgent/logstashagent.yml and starts accordingly
REM - Host mode: Starts native Python agent on Windows, then containers (without agent container)
REM - Embedded mode: Starts all containers including agent
REM
REM Usage:
REM   start_logstashui.bat          - Start with existing images
REM   start_logstashui.bat --rebuild - Rebuild images before starting

REM IMPORTANT: Don't enable delayed expansion yet - it breaks paths with exclamation marks
setlocal disabledelayedexpansion

REM Parse command line arguments
set REBUILD_FLAG=
if "%1"=="--rebuild" set REBUILD_FLAG=--build

echo ========================================
echo LogstashUI Startup
echo ========================================
echo.
echo Ensuring clean state - stopping any existing services...
echo.

REM Call stop script first to ensure clean state
REM Suppress pause at end of stop script
call "%~dp0stop_logstashui.bat" >nul 2>&1

echo.
echo ========================================
echo Starting LogstashUI
echo ========================================
echo.

REM Change to the repository root directory (parent of bin)
REM Use pushd to preserve the path with special characters
pushd "%~dp0.."

REM Debug: Show current directory
echo Current directory: %CD%
echo.

REM Check if logstashui.yml exists
if not exist "logstashui.yml" (
    echo ERROR: logstashui.yml not found!
    echo Expected location: %CD%\logstashui.yml
    echo.
    echo Directory contents:
    dir /b
    exit /b 1
)

echo Found logstashui.yml
echo.

REM Now enable delayed expansion for variable parsing
setlocal enabledelayedexpansion

REM Parse the simulation mode from logstashui.yml (under simulation.mode)
set MODE=embedded
for /f "tokens=2 delims=: " %%a in ('findstr /i "mode:" logstashui.yml') do (
    REM Get the first 'mode:' value which is simulation.mode
    if "!MODE!"=="embedded" set MODE=%%a
)

REM Remove any trailing comments or whitespace
set MODE=%MODE: =%
set MODE=%MODE:#=%

echo Detected mode: %MODE%
echo.

if /i "%MODE%"=="host" (
    echo ========================================
    echo HOST MODE DETECTED
    echo ========================================
    echo Starting LogstashAgent natively on Windows
    echo This allows the agent to control your host Logstash instance.
    echo.
    
    REM Check if Python is available
    python --version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python not found in PATH!
        echo Please install Python 3.9+ and ensure it's in your PATH.
        exit /b 1
    )
    
    REM Install/update Python dependencies for LogstashAgent
    echo Installing Python dependencies for LogstashAgent
    python -m pip install -r LogstashAgent\requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies!
        echo Please check that Python and pip are working correctly.
        exit /b 1
    )
    echo Dependencies installed successfully
    
    echo.
    echo Preparing LogstashAgent configuration
    REM Copy logstash_agent config from logstashui.yml to LogstashAgent/logstashagent.yml
    python bin\sync_config.py
    if errorlevel 1 (
        echo WARNING: Could not update agent config automatically
        echo Please ensure LogstashAgent\logstashagent.yml has correct paths
    )
    
    echo Starting LogstashAgent on port 9501
    cd LogstashAgent
    start "LogstashAgent" cmd /K "python -m uvicorn main:app --host 0.0.0.0 --port 9501"
    cd ..
    
    echo Waiting 5 seconds for agent to initialize
    ping 127.0.0.1 -n 6 >nul
    
    echo.
    echo ========================================
    echo Starting Docker containers (UI + Nginx only)
    echo ========================================
    echo Note: LogstashAgent container will NOT start (running natively instead)
    echo Note: Native agent runs on port 9501, nginx proxies from 9500 to 9501
    echo.
    
    REM Ensure agent container is stopped in host mode
    echo Stopping any existing containers
    docker-compose stop logstashagent 2>nul
    docker-compose rm -f logstashagent 2>nul
    
    REM Start only logstashui and nginx in detached mode
    REM Nginx will detect host mode and proxy to host.docker.internal:9501
    docker-compose up -d %REBUILD_FLAG% logstashui nginx
    
) else (
    echo ========================================
    echo EMBEDDED MODE DETECTED
    echo ========================================
    echo Starting all containers including embedded LogstashAgent
    echo Logstash will run inside the agent container.
    echo.
    
    REM Start all containers in detached mode with embedded profile
    docker-compose --profile embedded up -d %REBUILD_FLAG%
)

echo.
echo ========================================
echo LogstashUI Started Successfully
echo ========================================
echo.
echo Containers are running in the background.
echo To stop LogstashUI, run: stop_logstashui.bat
echo.
echo Access LogstashUI at: https://localhost
echo.

REM Restore original directory
popd
