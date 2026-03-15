@echo off
REM LogstashUI Startup Script
REM Detects mode from LogstashAgent/logstashagent.yml and starts accordingly
REM - Host mode: Starts native Python agent on Windows, then containers (without agent container)
REM - Embedded mode: Starts all containers including agent
REM
REM Usage:
REM   start_logstashui.bat          - Start with existing images
REM   start_logstashui.bat --rebuild - Rebuild images before starting
REM   start_logstashui.bat --update  - Pull latest code and images, then start

REM IMPORTANT: Don't enable delayed expansion yet - it breaks paths with exclamation marks
setlocal disabledelayedexpansion

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

echo Using Docker Compose command: %DOCKER_COMPOSE%
echo.

REM Parse command line arguments
set REBUILD_FLAG=
set UPDATE_MODE=0
if "%1"=="--rebuild" set REBUILD_FLAG=--build
if "%1"=="--update" set UPDATE_MODE=1

echo ========================================
echo LogstashUI Startup
echo ========================================
echo.
REM Handle update mode
if %UPDATE_MODE%==1 (
    echo ========================================
    echo UPDATE MODE
    echo ========================================
    echo Pulling latest code from git...
    echo.
    
    git pull
    if errorlevel 1 (
        echo WARNING: Git pull failed. Continuing with existing code...
        echo.
    ) else (
        echo Git pull successful!
        echo.
    )
    
    echo Stopping containers...
    call "%~dp0stop_logstashui.bat" >nul 2>&1
    
    echo.
    echo Pulling latest Docker images...
    %DOCKER_COMPOSE% pull
    if errorlevel 1 (
        echo WARNING: Failed to pull some images. Continuing...
        echo.
    ) else (
        echo Images pulled successfully!
        echo.
    )
) else (
    echo Ensuring clean state - stopping any existing services...
    echo.
    
    REM Call stop script first to ensure clean state
    REM Suppress pause at end of stop script
    call "%~dp0stop_logstashui.bat" >nul 2>&1
)

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

REM Ensure logstashui.yml exists (required for Docker volume mount)
REM If it doesn't exist, create a copy from logstashui.example.yml
if not exist "logstashui.yml" (
    if exist "logstashui.example.yml" (
        echo Creating logstashui.yml copy from logstashui.example.yml
        copy logstashui.example.yml logstashui.yml >nul
    ) else (
        echo ERROR: logstashui.example.yml not found!
        echo Current directory: %CD%
        exit /b 1
    )
)

REM Check for config file (logstashui.yml first, fallback to logstashui.example.yml)
if exist "logstashui.yml" (
    set CONFIG_FILE=logstashui.yml
) else if exist "logstashui.example.yml" (
    set CONFIG_FILE=logstashui.example.yml
) else (
    echo ERROR: No config file found!
    echo Expected logstashui.yml or logstashui.example.yml in project root.
    echo Current directory: %CD%
    echo.
    echo Directory contents:
    dir /b
    exit /b 1
)

echo Using config file: %CONFIG_FILE%
echo.

REM Now enable delayed expansion for variable parsing
setlocal enabledelayedexpansion

REM Parse the simulation mode from config file (under simulation.mode)
REM Search for the line with "# embedded | host" comment to identify the right mode line
set MODE=embedded
for /f "tokens=2 delims=: " %%a in ('findstr /C:"# embedded | host" !CONFIG_FILE!') do (
    set MODE=%%a
)

REM Remove any trailing comments or whitespace
set MODE=!MODE: =!
for /f "tokens=1 delims=#" %%a in ("!MODE!") do set MODE=%%a
set MODE=!MODE: =!

echo Detected mode: !MODE!
echo.

if /i "!MODE!"=="host" (
    goto HOST_MODE
) else (
    goto EMBEDDED_MODE
)

:HOST_MODE
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

REM Setup virtual environment for LogstashAgent
if not exist "LogstashAgent\.venv" (
    echo Creating virtual environment in LogstashAgent\.venv
    python -m venv LogstashAgent\.venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment!
        echo Please ensure Python venv module is available
        exit /b 1
    )
)

echo Activating virtual environment
call LogstashAgent\.venv\Scripts\activate.bat

REM Install/update Python dependencies for LogstashAgent
echo Installing Python dependencies for LogstashAgent
pip install -r LogstashAgent\requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies!
    echo Please check that Python and pip are working correctly.
    call LogstashAgent\.venv\Scripts\deactivate.bat
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

echo Starting LogstashAgent on port 9501 (localhost only)
cd LogstashAgent
REM Start uvicorn using the virtual environment's Python
start "LogstashAgent" cmd /K ".venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 9501"
cd ..

REM Deactivate virtual environment (agent is running in separate window)
call LogstashAgent\.venv\Scripts\deactivate.bat

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
%DOCKER_COMPOSE% stop logstashagent 2>nul
%DOCKER_COMPOSE% rm -f logstashagent 2>nul

REM Start only logstashui and nginx in detached mode
REM Nginx will detect host mode and proxy to host.docker.internal:9501
%DOCKER_COMPOSE% up -d %REBUILD_FLAG% logstashui nginx
goto END_MODE_SELECTION

:EMBEDDED_MODE
echo ========================================
echo EMBEDDED MODE DETECTED
echo ========================================
echo Starting all containers including embedded LogstashAgent
echo Logstash will run inside the agent container.
echo.

REM Start all containers in detached mode with embedded profile
%DOCKER_COMPOSE% --profile embedded up -d %REBUILD_FLAG%
goto END_MODE_SELECTION

:END_MODE_SELECTION

echo.
echo ========================================
echo LogstashUI Started Successfully
echo ========================================
echo.
echo Containers are running in the background.
echo To stop LogstashUI, run: stop_logstashui.bat
echo.
echo Access LogstashUI at: https://your_ip_or_hostname_here
echo.

REM Restore original directory
popd
