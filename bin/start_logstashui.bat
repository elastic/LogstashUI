@echo off
REM LogstashUI Startup Script
REM Detects simulation.mode from logstashui.yml / example and starts accordingly
REM - embedded: all containers including LogstashAgent
REM - host (LEGACY): native agent on :9501 + UI/nginx only - not enrolled simulate@N
REM Preferred multi-instance sim: enroll a Simulate policy (see host_mode.md)
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

REM ---------------------------------------------------------------------------
REM Host identity for product UI TLS SANs (containers cannot see Docker host IPs)
REM Uses PowerShell to collect hostname / non-loopback IPs / reverse-DNS FQDN.
REM Operator can pre-set any of these vars to override auto-detection.
REM ---------------------------------------------------------------------------
set "_TLS_TMP=%TEMP%\logstashui_tls_%RANDOM%.txt"
powershell -NoProfile -NonInteractive -Command "$ErrorActionPreference='SilentlyContinue'; $hn=[System.Net.Dns]::GetHostName(); try{$ips=(Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred | Where-Object{$_.IPAddress -notmatch '^127\.' -and $_.IPAddress -ne '0.0.0.0'} | Select-Object -ExpandProperty IPAddress) -join ','}catch{$ips=''}; $fqdn=$hn; try{$e=[System.Net.Dns]::GetHostEntry($hn); if($e.HostName -match '\.'){$fqdn=$e.HostName}}catch{}; $sans=if($ips){$fqdn+','+$ips}else{$fqdn}; $csrf='https://localhost:8443,https://127.0.0.1:8443'; if($fqdn){$csrf+=',https://'+$fqdn+':8443'}; ($ips -split ',' | Where-Object{$_})|ForEach-Object{$csrf+=',https://'+$_+':8443'}; Write-Output ('LOGSTASHUI_HOST_HOSTNAME='+$fqdn); Write-Output ('LOGSTASHUI_HOST_IPS='+$ips); Write-Output ('LOGSTASHUI_TLS_SANS='+$sans); Write-Output ('CSRF_TRUSTED_ORIGINS='+$csrf)" > "%_TLS_TMP%" 2>nul
if exist "%_TLS_TMP%" (
    for /f "usebackq tokens=1* delims==" %%K in ("%_TLS_TMP%") do (
        if /i "%%K"=="LOGSTASHUI_HOST_HOSTNAME" if not defined LOGSTASHUI_HOST_HOSTNAME set "LOGSTASHUI_HOST_HOSTNAME=%%L"
        if /i "%%K"=="LOGSTASHUI_HOST_IPS" if not defined LOGSTASHUI_HOST_IPS set "LOGSTASHUI_HOST_IPS=%%L"
        if /i "%%K"=="LOGSTASHUI_TLS_SANS" if not defined LOGSTASHUI_TLS_SANS set "LOGSTASHUI_TLS_SANS=%%L"
        if /i "%%K"=="CSRF_TRUSTED_ORIGINS" if not defined CSRF_TRUSTED_ORIGINS set "CSRF_TRUSTED_ORIGINS=%%L"
    )
    del "%_TLS_TMP%" >nul 2>&1
)
set _TLS_TMP=
echo Host TLS SAN injection for UI product cert:
echo   LOGSTASHUI_HOST_HOSTNAME=%LOGSTASHUI_HOST_HOSTNAME%
echo   LOGSTASHUI_HOST_IPS=%LOGSTASHUI_HOST_IPS%
echo   LOGSTASHUI_TLS_SANS=%LOGSTASHUI_TLS_SANS%
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

REM Compose file set: smoke override tags local images and enables build:.
REM Used whenever REBUILD_FLAG is set so --rebuild actually compiles this tree.
set "COMPOSE_FILES="
if not "!REBUILD_FLAG!"=="" (
    if exist "docker\docker-compose.smoke.yml" (
        set "COMPOSE_FILES=-f docker-compose.yml -f docker-compose.smoke.yml"
    )
)

if /i "!MODE!"=="host" (
    goto HOST_MODE
) else (
    goto EMBEDDED_MODE
)

:HOST_MODE
echo ========================================
echo LEGACY HOST MODE DETECTED
echo ========================================
echo Starting a native LogstashAgent (FastAPI + supervisor) on Windows.
echo.
echo NOTE: This is a LEGACY local sim path (simulation.mode: host).
echo It is NOT an enrolled mode:simulate / lsagent-simulate@N instance.
echo Prefer enrolling a Simulate policy agent for multi-instance sim.
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
cd ..

echo.
echo ========================================
echo Starting Docker UI first (HTTPS :8443), then legacy native agent
echo ========================================
echo Note: LogstashAgent container will NOT start (legacy native agent instead)
echo Note: Native agent HTTPS on port 9501; UI uses LOGSTASH_AGENT_URL=https://host.docker.internal:9501
echo.

REM Ensure agent container is stopped for legacy host path
echo Stopping any existing containers
cd docker
%DOCKER_COMPOSE% stop logstashagent 2>nul
%DOCKER_COMPOSE% rm -f logstashagent 2>nul

REM UI must start before the agent so TLS material is issued first
if not defined LOGSTASH_AGENT_URL set "LOGSTASH_AGENT_URL=https://host.docker.internal:9501"
if not defined LOGSTASHUI_AGENT_CSR_SECRET set "LOGSTASHUI_AGENT_CSR_SECRET=logstashui-compose-dev"
%DOCKER_COMPOSE% !COMPOSE_FILES! up -d !REBUILD_FLAG! logstashui
cd ..

echo Waiting 8 seconds for UI TLS material...
ping 127.0.0.1 -n 9 >nul

echo Starting LogstashAgent on port 9501 (HTTPS when cert issued)
cd LogstashAgent
if not defined LOGSTASH_UI_URL set "LOGSTASH_UI_URL=https://localhost:8443"
if not defined LOGSTASHUI_AGENT_CSR_SECRET set "LOGSTASHUI_AGENT_CSR_SECRET=logstashui-compose-dev"
set "LOGSTASH_AGENT_PORT=9501"
start "LogstashAgent" cmd /K "uv run python -m logstashagent.main --mode embedded"
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
%DOCKER_COMPOSE% !COMPOSE_FILES! --profile embedded up -d !REBUILD_FLAG!
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
echo Access LogstashUI at: https://your_ip_or_hostname_here:8443
echo.

REM Restore original directory
popd
