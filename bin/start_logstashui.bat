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

REM Check for required dependencies
echo Checking dependencies...
set MISSING_DEPS=

REM Check for Docker
docker --version >nul 2>&1
if errorlevel 1 (
    set MISSING_DEPS=%MISSING_DEPS% docker
)

REM Check for Git
git --version >nul 2>&1
if errorlevel 1 (
    set MISSING_DEPS=%MISSING_DEPS% git
)

if not "%MISSING_DEPS%"=="" (
    echo.
    echo ERROR: Missing required dependencies:%MISSING_DEPS%
    echo.
    echo Please install the following:
    echo %MISSING_DEPS% | findstr "docker" >nul
    if not errorlevel 1 (
        echo   - Docker Desktop: https://www.docker.com/get-started/
    )
    echo %MISSING_DEPS% | findstr "git" >nul
    if not errorlevel 1 (
        echo   - Git: https://git-scm.com/download/win
    )
    echo.
    pause
    exit /b 1
)
echo Dependencies check passed.
echo.

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
    echo Switching to main branch...
    echo.
    
    git checkout main
    if errorlevel 1 (
        echo WARNING: Failed to switch to main branch. Continuing anyway...
        echo.
    ) else (
        echo Switched to main branch successfully!
        echo.
    )
    
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
if not exist "src\logstashui\logstashui.yml" (
    if exist "src\logstashui\logstashui.example.yml" (
        echo Creating logstashui.yml copy from logstashui.example.yml
        copy src\logstashui\logstashui.example.yml src\logstashui\logstashui.yml >nul
    ) else (
        echo ERROR: src\logstashui\logstashui.example.yml not found!
        echo Current directory: %CD%
        exit /b 1
    )
)

REM Check for config file (logstashui.yml first, fallback to logstashui.example.yml)
if exist "src\logstashui\logstashui.yml" (
    set CONFIG_FILE=src\logstashui\logstashui.yml
) else if exist "src\logstashui\logstashui.example.yml" (
    set CONFIG_FILE=src\logstashui\logstashui.example.yml
) else (
    echo ERROR: No config file found!
    echo Expected logstashui.yml or logstashui.example.yml in src\logstashui\
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

REM Check if uv is available
uv --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv not found in PATH!
    echo Please install uv from: https://docs.astral.sh/uv/getting-started/installation/
    echo.
    echo Quick install: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    exit /b 1
)

REM Clone LogstashAgent if it doesn't exist
if not exist "LogstashAgent" (
    echo LogstashAgent directory not found, cloning from GitHub...
    echo.
    git clone https://github.com/elastic/LogstashAgent.git
    if errorlevel 1 (
        echo ERROR: Failed to clone LogstashAgent repository!
        echo Please check your internet connection and Git installation.
        exit /b 1
    )
    echo LogstashAgent cloned successfully!
    echo.
) else (
    echo LogstashAgent directory found.
    echo.
)

echo.
echo Preparing LogstashAgent configuration
REM Copy logstash_agent config from logstashui.yml to LogstashAgent/src/logstashagent/logstashagent.yml
python bin\sync_config.py
if errorlevel 1 (
    echo WARNING: Could not update agent config automatically
    echo Please ensure LogstashAgent\src\logstashagent\logstashagent.yml has correct paths
)

REM Install/update Python dependencies for LogstashAgent using uv
echo Installing Python dependencies for LogstashAgent with uv
cd LogstashAgent
uv sync
if errorlevel 1 (
    echo ERROR: Failed to install dependencies with uv!
    echo Please check that uv is working correctly.
    exit /b 1
)
echo Dependencies installed successfully

echo Starting LogstashAgent on port 9501 (localhost only)
cd LogstashAgent
REM Start uvicorn using uv run
start "LogstashAgent" cmd /K "uv run uvicorn logstashagent.main:app --host 127.0.0.1 --port 9501"
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
cd docker
%DOCKER_COMPOSE% stop logstashagent 2>nul
%DOCKER_COMPOSE% rm -f logstashagent 2>nul

REM Start only logstashui and nginx in detached mode
REM Nginx will detect host mode and proxy to host.docker.internal:9501
%DOCKER_COMPOSE% up -d %REBUILD_FLAG% logstashui nginx
cd ..
goto END_MODE_SELECTION

:EMBEDDED_MODE
echo ========================================
echo EMBEDDED MODE DETECTED
echo ========================================
echo Starting all containers including embedded LogstashAgent
echo Logstash will run inside the agent container.
echo.

REM Start all containers in detached mode with embedded profile
cd docker
%DOCKER_COMPOSE% --profile embedded up -d %REBUILD_FLAG%
cd ..
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
