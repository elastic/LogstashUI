#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import os
import subprocess
import threading
import time
import logging
import signal
import psutil
import shutil
from typing import Optional
from .logstash_api import LogstashAPI
from . import slots

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to INFO level for supervisor

class LogstashSupervisor:
    """
    Supervises the Logstash process with automatic restart on:
    1. Process crash/OOM
    2. JVM heap usage > 90% for 30+ seconds
    3. RSS memory dynamically calculated based on heap size
    
    Currently always runs in simulation mode (supervised Logstash).
    TODO: Add detection for production vs simulation nodes in the future.
    """
    
    def __init__(self, config: dict = None):
        self.process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.should_run = True
        
        # Load configuration
        self.config = config or {}
        self.simulation_mode_type = self.config.get('simulation_mode', 'embedded')  # 'embedded' or 'host'
        self.logstash_binary = self.config.get('logstash_binary', '/usr/share/logstash/bin/logstash')
        self.logstash_settings = self.config.get('logstash_settings', '/etc/logstash/')
        self.logstash_log_path = self.config.get('logstash_log_path', '/var/log/logstash')
        
        # Ensure settings path ends with /
        if not self.logstash_settings.endswith('/'):
            self.logstash_settings += '/'
        
        # Ensure log path does NOT end with /
        if self.logstash_log_path.endswith('/'):
            self.logstash_log_path = self.logstash_log_path.rstrip('/')
        
        # TODO: In the future, detect if this is a simulation node vs production node
        # For now, always default to simulation mode (supervised Logstash with memory monitoring)
        # Production nodes would run Logstash without supervision
        self.simulation_mode = True
        
        # Memory thresholds - CONSERVATIVE: Only restart in truly critical situations
        # Manager relies on sim node status, so avoid operational restarts
        self.heap_threshold_percent = 95.0  # Only restart at 95% heap (was 90%)
        self.threshold_duration_seconds = 60.0  # Wait 60s before restart (was 30s)
        
        # RSS thresholds will be calculated dynamically based on JVM heap size
        # CONSERVATIVE: Only restart when RSS is critically high to prevent stunned state
        # With 4GB heap, this allows up to 6GB RSS before restart
        # (JVM overhead + off-heap memory + OS buffers + safety margin)
        self.rss_critical_multiplier = 1.5  # Restart at 150% of heap (was 1.2x)
        self.heap_max_gb: Optional[float] = None  # Will be fetched from Logstash API
        
        # Tracking
        self.high_memory_start_time: Optional[float] = None
        self.restart_count = 0
        self.api_unresponsive_count = 0
        self.api_unresponsive_threshold = 6  # Restart after 6 consecutive API failures (30s total, was 3)
        self.pipeline_mismatch_start_time: Optional[float] = None
        self.pipeline_mismatch_threshold_seconds = 30.0  # Restart after 30s of mismatch (was 15s)
        
        # Logstash health state for request queuing
        self.is_healthy = False  # Set to True once Logstash API responds
        self.is_restarting = False  # Set to True during restart process
        
        logger.info(f"LogstashSupervisor initialized (mode={self.simulation_mode_type}, binary={self.logstash_binary}, settings={self.logstash_settings})")
    
    def setup_host_mode(self):
        """
        Set up host mode by copying all config files from container to host.
        This overwrites the host's Logstash configuration with our simulation configs.
        """
        logger.info(f"Setting up host mode - copying configs to {self.logstash_settings}")
        
        # Source directory - check local first (native mode), then Docker path
        local_config_dir = os.path.join(os.path.dirname(__file__), "config")
        docker_config_dir = "/app/config"
        
        if os.path.exists(local_config_dir):
            container_config_dir = local_config_dir
            logger.info(f"Using local config directory: {container_config_dir}")
        elif os.path.exists(docker_config_dir):
            container_config_dir = docker_config_dir
            logger.info(f"Using Docker config directory: {container_config_dir}")
        else:
            raise FileNotFoundError(f"Config directory not found. Tried: {local_config_dir}, {docker_config_dir}")
        
        # Files to copy directly to settings root
        config_files = [
            'jvm.options',
            'log4j2.properties',
            'logstash.yml',
            'pipelines.yml'
        ]
        
        # Pipeline config files to copy to conf.d
        pipeline_files = [
            'simulate_start.conf',
            'simulate_end.conf'
        ]
        
        try:
            # Create settings directory if it doesn't exist
            os.makedirs(self.logstash_settings, exist_ok=True)
            logger.info(f"Ensured settings directory exists: {self.logstash_settings}")
            
            # Copy config files to settings root
            for filename in config_files:
                src = os.path.join(container_config_dir, filename)
                dst = os.path.join(self.logstash_settings, filename)
                
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    logger.info(f"Copied {filename} to {dst}")
                else:
                    logger.warning(f"Source file not found: {src}")
            
            # Update log4j2.properties with custom log path if configured
            log4j2_path = os.path.join(self.logstash_settings, 'log4j2.properties')
            if os.path.exists(log4j2_path):
                with open(log4j2_path, 'r') as f:
                    log4j2_content = f.read()
                
                # Replace /var/log/logstash with custom log path (use forward slashes for consistency)
                normalized_log_path = self.logstash_log_path.replace('\\', '/')
                log4j2_content = log4j2_content.replace('/var/log/logstash', normalized_log_path)
                
                with open(log4j2_path, 'w') as f:
                    f.write(log4j2_content)
                logger.info(f"Updated log4j2.properties with log path: {normalized_log_path}")
            
            # Create config directory for static pipeline configs (simulate_start.conf, simulate_end.conf)
            config_path = os.path.join(self.logstash_settings, 'config')
            os.makedirs(config_path, exist_ok=True)
            logger.info(f"Created config directory: {config_path}")
            
            # Copy pipeline files to config/ (not conf.d/)
            for filename in pipeline_files:
                src = os.path.join(container_config_dir, filename)
                dst = os.path.join(config_path, filename)
                
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    logger.info(f"Copied {filename} to {dst}")
                else:
                    logger.warning(f"Source file not found: {src}")
            
            # Create conf.d directory for dynamic pipeline configs (slot pipelines)
            conf_d_path = os.path.join(self.logstash_settings, 'conf.d')
            os.makedirs(conf_d_path, exist_ok=True)
            logger.info(f"Created conf.d directory for dynamic pipelines: {conf_d_path}")
            
            # Update pipelines.yml to use correct paths for host mode
            pipelines_yml_path = os.path.join(self.logstash_settings, 'pipelines.yml')
            if os.path.exists(pipelines_yml_path):
                with open(pipelines_yml_path, 'r') as f:
                    content = f.read()
                
                # Replace container paths with host paths
                # Static pipelines (simulate_start/end) go in config/
                # Convert backslashes to forward slashes for YAML compatibility on Windows
                host_config_path = f'{self.logstash_settings}config/'.replace('\\', '/')
                
                # Replace both quoted and unquoted paths
                # Handle quotes with and without spaces
                content = content.replace('path.config: "/etc/logstash/config/', f'path.config: "{host_config_path}')
                content = content.replace('path.config: /etc/logstash/config/', f'path.config: {host_config_path}')
                content = content.replace('"/etc/logstash/config/', f'"{host_config_path}')
                content = content.replace('/etc/logstash/config/', host_config_path)
                
                with open(pipelines_yml_path, 'w') as f:
                    f.write(content)
                logger.info(f"Updated pipelines.yml with host paths (using forward slashes): {host_config_path}")
            
            # Create pipeline-metadata directory
            metadata_dir = os.path.join(self.logstash_settings, 'pipeline-metadata')
            os.makedirs(metadata_dir, exist_ok=True)
            logger.info(f"Created pipeline-metadata directory: {metadata_dir}")
            
            # Create log directory if it doesn't exist
            os.makedirs(self.logstash_log_path, exist_ok=True)
            logger.info(f"Ensured log directory exists: {self.logstash_log_path}")
            
            logger.info("Host mode setup complete")
            
        except Exception as e:
            logger.error(f"Error setting up host mode: {e}", exc_info=True)
            raise
    
    def start_logstash(self):
        """Start the Logstash process"""
        logger.debug("[START] start_logstash() called")
        if self.process and self.process.poll() is not None:
            logger.warning("Logstash is already running")
            logger.debug(f"[START] Existing process PID: {self.process.pid}")
            return
        
        logger.info(f"Starting Logstash in {self.simulation_mode_type} mode...")
        logger.debug("[START] Preparing environment variables")
        
        # Setup host mode if needed (copy configs to host)
        if self.simulation_mode_type == 'host':
            logger.info("Host mode detected - setting up host configuration")
            self.setup_host_mode()
        
        # Determine lock file path based on mode
        if self.simulation_mode_type == 'embedded':
            lock_file = "/usr/share/logstash/data/.lock"
        else:  # host mode
            # Derive from logstash binary path
            # /usr/share/logstash/bin/logstash -> /usr/share/logstash/data/.lock
            logstash_home = os.path.dirname(os.path.dirname(self.logstash_binary))
            lock_file = os.path.join(logstash_home, "data", ".lock")
        
        # Clean up lock file from previous instance
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                logger.info(f"Removed stale lock file: {lock_file}")
            except Exception as e:
                logger.warning(f"Failed to remove lock file {lock_file}: {e}")
        
        # Prepare environment - copy all environment variables
        env = os.environ.copy()
        
        # Set log4j config path based on mode
        if self.simulation_mode_type == 'embedded':
            env['LS_JAVA_OPTS'] = "-Dlog4j.configurationFile=/etc/logstash/log4j2.properties"
        else:  # host mode
            log4j_path = os.path.join(self.logstash_settings, 'log4j2.properties')
            env['LS_JAVA_OPTS'] = f"-Dlog4j.configurationFile={log4j_path}"
        
        # Ensure LOGSTASH_URL is available to Logstash
        # This is critical for http output plugin in simulate_end.conf and simulate_start.conf
        # Always set based on mode to ensure correct routing, unless explicitly overridden
        existing_url = env.get('LOGSTASH_URL', '')
        
        # Only override if not explicitly set (i.e., using defaults)
        # Docker-compose sets this to https://nginx, which we should preserve
        # Dockerfile default is http://host.docker.internal:8080
        if not existing_url or existing_url in ['http://host.docker.internal:8080', 'http://localhost:8080']:
            # Set based on mode:
            # - Host mode: Logstash runs natively on host, access Django via nginx HTTPS proxy on localhost:443
            #   https://localhost works from both inside and outside containers
            # - Embedded mode: Container mode -> use host.docker.internal for standalone builds
            if self.simulation_mode_type == 'host':
                env['LOGSTASH_URL'] = 'https://localhost'
            else:
                env['LOGSTASH_URL'] = 'http://host.docker.internal:8080'
            logger.info(f"LOGSTASH_URL set for {self.simulation_mode_type} mode: {env['LOGSTASH_URL']}")
        else:
            logger.info(f"LOGSTASH_URL already set (preserving): {env['LOGSTASH_URL']}")
        
        # Validate binary exists
        if not os.path.exists(self.logstash_binary):
            error_msg = f"Logstash binary not found at: {self.logstash_binary}"
            logger.error(error_msg)
            logger.error("For host mode, ensure:")
            logger.error("1. If running natively: Use Windows paths (C:\\logstash-9.3.1\\...\\bin\\logstash.bat)")
            logger.error("2. If running in container: Mount host directory and use container paths (/host/logstash/bin/logstash)")
            logger.error("3. Start with bin/start_logstashui.bat to automatically detect mode")
            raise FileNotFoundError(error_msg)
        
        # Make binary executable (needed for mounted Windows files on Linux)
        # Skip on Windows as chmod doesn't work the same way
        if os.name != 'nt':
            try:
                os.chmod(self.logstash_binary, 0o755)
                logger.debug(f"Set executable permissions on {self.logstash_binary}")
            except Exception as e:
                logger.warning(f"Could not set executable permissions: {e}")
        
        # Start Logstash with configured paths
        logger.debug("[START] Launching Logstash subprocess")
        logger.info(f"Executing: {self.logstash_binary} --path.settings {self.logstash_settings}")
        
        # Prepare subprocess arguments
        # On Windows, strip trailing slashes/backslashes; on Linux, strip trailing forward slashes
        settings_path = self.logstash_settings.rstrip('/').rstrip('\\')
        
        # preexec_fn only works on Unix-like systems
        # Use DEVNULL for stdout/stderr to prevent pipe blocking on Windows
        # Logstash writes to its own log files configured via log4j2.properties
        popen_kwargs = {
            'env': env,
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL
        }
        
        if os.name != 'nt':
            popen_kwargs['preexec_fn'] = os.setsid  # Create new process group for clean shutdown (Unix only)
        
        # On Linux host mode, run as logstash user (not root)
        # Logstash refuses to run as root for security reasons
        if os.name != 'nt' and self.simulation_mode_type == 'host':
            # Use sudo -E to run as logstash user and preserve environment variables (especially LOGSTASH_URL)
            cmd = ['sudo', '-E', '-u', 'logstash', self.logstash_binary, '--path.settings', settings_path]
            logger.info(f"Running as logstash user with preserved env: {' '.join(cmd)}")
            logger.info(f"LOGSTASH_URL will be: {env.get('LOGSTASH_URL', 'NOT SET')}")
        else:
            cmd = [self.logstash_binary, '--path.settings', settings_path]
        
        self.process = subprocess.Popen(
            cmd,
            **popen_kwargs
        )
        
        logger.info(f"Logstash started with PID {self.process.pid}")
        if os.name != 'nt':
            logger.debug(f"[START] Process group ID: {os.getpgid(self.process.pid)}")
        else:
            logger.debug("[START] Running on Windows (process groups not applicable)")
        
        # Start monitoring thread if in simulation mode
        if self.simulation_mode and not self.monitor_thread:
            logger.debug("[START] Starting monitoring thread")
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("Memory monitoring thread started")
            logger.debug(f"[START] Monitor thread name: {self.monitor_thread.name}")
        else:
            logger.debug(f"[START] Monitoring thread not started - simulation_mode={self.simulation_mode}, monitor_thread_exists={self.monitor_thread is not None}")
    
    def stop_logstash(self, graceful=True):
        """Stop the Logstash process"""
        logger.debug(f"[STOP] stop_logstash() called with graceful={graceful}")
        if not self.process:
            logger.debug("[STOP] No process to stop")
            return
        
        logger.info(f"Stopping Logstash (PID {self.process.pid}, graceful={graceful})...")
        logger.debug(f"[STOP] Process state: poll={self.process.poll()}")
        
        try:
            # Check if process is already dead
            if self.process.poll() is not None:
                logger.info(f"Logstash process already terminated (exit code: {self.process.returncode})")
                # Still cleanup any orphaned child processes
                self._cleanup_orphaned_processes()
                self.process = None
                return
            
            if graceful:
                # Send SIGTERM for graceful shutdown
                try:
                    pgid = os.getpgid(self.process.pid)
                    logger.debug(f"[STOP] Sending SIGTERM to process group {pgid}")
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    logger.warning("[STOP] Process already terminated before SIGTERM could be sent")
                    self._cleanup_orphaned_processes()
                    self.process = None
                    return
                
                # Wait up to 30 seconds for graceful shutdown
                logger.debug("[STOP] Waiting up to 30s for graceful shutdown")
                try:
                    self.process.wait(timeout=30)
                    logger.info("Logstash stopped gracefully")
                    logger.debug(f"[STOP] Process exit code: {self.process.returncode}")
                except subprocess.TimeoutExpired:
                    logger.warning("Graceful shutdown timed out, forcing kill")
                    logger.debug("[STOP] Sending SIGKILL to force termination")
                    try:
                        pgid = os.getpgid(self.process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                        self.process.wait()
                        logger.debug(f"[STOP] Process killed, exit code: {self.process.returncode}")
                    except ProcessLookupError:
                        logger.warning("[STOP] Process already terminated before SIGKILL could be sent")
            else:
                # Force kill
                try:
                    pgid = os.getpgid(self.process.pid)
                    logger.debug(f"[STOP] Sending SIGKILL to process group {pgid}")
                    os.killpg(pgid, signal.SIGKILL)
                    self.process.wait()
                    logger.info("Logstash killed")
                    logger.debug(f"[STOP] Process exit code: {self.process.returncode}")
                except ProcessLookupError:
                    logger.warning("[STOP] Process terminated unexpectedly")
        finally:
            # Aggressively cleanup any remaining Logstash processes
            self._cleanup_orphaned_processes()
            self.process = None
            logger.debug("[STOP] Process reference cleared")
    
    def _cleanup_orphaned_processes(self):
        """Kill any orphaned Logstash/Java processes that might be holding ports"""
        try:
            import psutil
            killed_count = 0
            
            # Find all java processes that look like Logstash
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Check if it's a Java process with logstash in the command line
                    if proc.info['name'] == 'java' and proc.info['cmdline']:
                        cmdline = ' '.join(proc.info['cmdline'])
                        if 'logstash' in cmdline.lower():
                            logger.warning(f"Found orphaned Logstash process PID {proc.info['pid']}, killing it")
                            proc.kill()
                            proc.wait(timeout=5)
                            killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
            
            if killed_count > 0:
                logger.info(f"Cleaned up {killed_count} orphaned Logstash process(es)")
                # Give the OS time to release ports
                import time
                time.sleep(2)
        except ImportError:
            logger.debug("psutil not available, skipping orphaned process cleanup")
        except Exception as e:
            logger.error(f"Error during orphaned process cleanup: {e}")
    
    def restart_logstash(self, reason: str = "Manual restart"):
        """Restart the Logstash process"""
        self.restart_count += 1
        self.is_restarting = True
        self.is_healthy = False
        logger.warning(f"Restarting Logstash (restart #{self.restart_count}): {reason}")
        logger.debug(f"[RESTART] Restart initiated - count: {self.restart_count}, reason: {reason}")
        
        # Evict all slots and clean up conf.d BEFORE stopping Logstash
        # This prevents Logstash from reloading old pipelines on restart
        logger.info("Evicting all slots and cleaning up conf.d before restart...")
        logger.debug("[RESTART] Calling evict_all_slots_and_cleanup()")
        try:
            evicted_slots = slots.evict_all_slots_and_cleanup()
            logger.info(f"Successfully evicted {len(evicted_slots)} slots and cleaned up conf.d")
            logger.debug(f"[RESTART] Evicted slots: {evicted_slots}")
        except Exception as e:
            logger.error(f"Error during slot eviction and cleanup: {e}")
            logger.debug(f"[RESTART] Eviction exception details", exc_info=True)
        
        logger.debug("[RESTART] Stopping Logstash")
        self.stop_logstash(graceful=True)
        
        # Brief pause to ensure clean shutdown
        logger.debug("[RESTART] Pausing 2s for clean shutdown")
        time.sleep(2)
        
        logger.debug("[RESTART] Starting Logstash")
        self.start_logstash()
        
        # Reset memory tracking
        logger.debug("[RESTART] Resetting all timers")
        self.high_memory_start_time = None
        self.pipeline_mismatch_start_time = None
        self.is_restarting = False
        # is_healthy will be set to True once API responds in monitoring loop
        logger.debug("[RESTART] Restart complete")
    
    def _get_expected_slot_pipelines(self) -> set:
        """
        Get the set of pipeline names that should be running based on allocated slots.
        
        Returns:
            Set of expected pipeline names (e.g., {'slot1-filter1', 'slot2-filter1'})
        """
        logger.debug("[SLOTS] Getting expected slot pipelines")
        try:
            import LogstashAgent.src.logstashagent.slots
            slot_state = slots.get_slot_state()
            expected_pipelines = set()
            logger.debug(f"[SLOTS] Retrieved {len(slot_state)} slots from state")
            
            for slot_id, slot_data in slot_state.items():
                pipelines = slot_data.get('pipelines', [])
                logger.debug(f"[SLOTS] Slot {slot_id} has {len(pipelines)} pipeline(s)")
                for idx in range(1, len(pipelines) + 1):
                    pipeline_name = f"slot{slot_id}-filter{idx}"
                    expected_pipelines.add(pipeline_name)
                    logger.debug(f"[SLOTS] Added expected pipeline: {pipeline_name}")
            
            logger.debug(f"[SLOTS] Total expected pipelines: {len(expected_pipelines)}")
            return expected_pipelines
        except Exception as e:
            logger.error(f"Error getting expected slot pipelines: {e}")
            logger.debug("[SLOTS] Exception details", exc_info=True)
            return set()
    
    def _get_jvm_heap_usage(self) -> Optional[float]:
        """Get JVM heap usage percentage from Logstash API"""
        logger.debug("[HEAP] Checking JVM heap usage")
        try:
            with LogstashAPI(timeout=2.0) as api:
                stats = api.get_node_stats()
                jvm = stats.get('jvm', {})
                mem = jvm.get('mem', {})
                heap_used = mem.get('heap_used_in_bytes', 0)
                heap_max = mem.get('heap_max_in_bytes', 1)
                logger.debug(f"[HEAP] Raw values - used: {heap_used} bytes, max: {heap_max} bytes")
                
                # Cache heap_max_gb for RSS threshold calculation
                if heap_max > 0 and self.heap_max_gb is None:
                    self.heap_max_gb = heap_max / (1024 ** 3)
                    logger.info(f"JVM heap max detected: {self.heap_max_gb:.2f}GB")
                    logger.info(f"RSS critical threshold: {self.heap_max_gb * self.rss_critical_multiplier:.2f}GB ({self.rss_critical_multiplier}x heap - immediate restart)")
                    logger.debug(f"[HEAP] Cached heap_max_gb for RSS calculations")
                
                if heap_max > 0:
                    percent = (heap_used / heap_max) * 100.0
                    logger.debug(f"[HEAP] Heap usage: {percent:.2f}%")
                    return percent
        except Exception as e:
            logger.debug(f"Could not get JVM heap usage: {e}")
            logger.debug("[HEAP] API call failed", exc_info=True)
        
        logger.debug("[HEAP] Returning None (no data available)")
        return None
    
    def _get_rss_memory_gb(self) -> Optional[float]:
        """Get RSS memory usage in GB for Logstash process"""
        logger.debug("[RSS] Checking RSS memory usage")
        if not self.process or self.process.poll() is not None:
            logger.debug("[RSS] No active process")
            return None
        
        try:
            proc = psutil.Process(self.process.pid)
            # Get memory for process and all children
            total_rss = proc.memory_info().rss
            logger.debug(f"[RSS] Parent process RSS: {total_rss / (1024**3):.3f}GB")
            
            children = proc.children(recursive=True)
            logger.debug(f"[RSS] Found {len(children)} child processes")
            for child in children:
                try:
                    child_rss = child.memory_info().rss
                    total_rss += child_rss
                    logger.debug(f"[RSS] Child PID {child.pid} RSS: {child_rss / (1024**3):.3f}GB")
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    logger.debug(f"[RSS] Could not get child process memory: {e}")
                    pass
            
            rss_gb = total_rss / (1024 ** 3)  # Convert bytes to GB
            logger.debug(f"[RSS] Total RSS: {rss_gb:.3f}GB")
            return rss_gb
        except Exception as e:
            logger.debug(f"Could not get RSS memory: {e}")
            logger.debug("[RSS] Exception details", exc_info=True)
        
        logger.debug("[RSS] Returning None (no data available)")
        return None
    
    def _check_pipeline_mismatch(self) -> Optional[str]:
        """
        Check if running pipelines match expected slot pipelines.
        Returns restart reason if mismatch persists for 15+ seconds.
        """
        logger.debug("[MISMATCH] Checking pipeline mismatch")
        try:
            with LogstashAPI(timeout=2.0) as api:
                # Get pipelines from health report
                logger.debug("[MISMATCH] Fetching health report")
                running_pipelines = set(api.get_running_pipelines_from_health())
                logger.debug(f"[MISMATCH] Health report returned {len(running_pipelines)} pipelines: {running_pipelines}")
                
                # Get expected pipelines from slots
                expected_pipelines = self._get_expected_slot_pipelines()
                logger.debug(f"[MISMATCH] Expected {len(expected_pipelines)} pipelines: {expected_pipelines}")
                
                # Filter to only slot pipelines (ignore simulate-start, simulate-end)
                running_slot_pipelines = {p for p in running_pipelines if p.startswith('slot')}
                logger.debug(f"[MISMATCH] Filtered to {len(running_slot_pipelines)} slot pipelines: {running_slot_pipelines}")
                
                # Check if they match
                if running_slot_pipelines != expected_pipelines:
                    if self.pipeline_mismatch_start_time is None:
                        self.pipeline_mismatch_start_time = time.time()
                        missing = expected_pipelines - running_slot_pipelines
                        extra = running_slot_pipelines - expected_pipelines
                        logger.warning(f"[TIMER START] Pipeline mismatch detected at {time.time():.2f}")
                        logger.warning(f"  Expected: {expected_pipelines}")
                        logger.warning(f"  Running: {running_slot_pipelines}")
                        if missing:
                            logger.warning(f"  Missing pipelines: {missing}")
                        if extra:
                            logger.warning(f"  Extra pipelines: {extra}")
                        logger.debug(f"[TIMER] Pipeline mismatch timer started, will restart after {self.pipeline_mismatch_threshold_seconds}s")
                    else:
                        duration = time.time() - self.pipeline_mismatch_start_time
                        logger.debug(f"[TIMER] Pipeline mismatch ongoing: {duration:.1f}s / {self.pipeline_mismatch_threshold_seconds}s")
                        if duration >= self.pipeline_mismatch_threshold_seconds:
                            missing = expected_pipelines - running_slot_pipelines
                            extra = running_slot_pipelines - expected_pipelines
                            logger.warning(f"[TIMER EXPIRED] Pipeline mismatch threshold reached: {duration:.0f}s")
                            return f"Pipeline mismatch for {duration:.0f}s (expected: {len(expected_pipelines)}, running: {len(running_slot_pipelines)}, missing: {missing}, extra: {extra})"
                else:
                    # Pipelines match - reset tracking
                    if self.pipeline_mismatch_start_time is not None:
                        duration = time.time() - self.pipeline_mismatch_start_time
                        logger.info(f"[TIMER RESET] Pipeline mismatch resolved after {duration:.1f}s")
                        self.pipeline_mismatch_start_time = None
                    else:
                        logger.debug(f"[TIMER] Pipelines match - expected: {len(expected_pipelines)}, running: {len(running_slot_pipelines)}")
        except Exception as e:
            logger.debug(f"Could not check pipeline mismatch: {e}")
            logger.debug("[MISMATCH] Exception details", exc_info=True)
        
        logger.debug("[MISMATCH] Returning None (no restart needed)")
        return None
    
    def _check_memory_thresholds(self) -> Optional[str]:
        """
        Check if memory thresholds are exceeded.
        Returns restart reason immediately if RSS exceeds heap size (prevents stunned state).
        """
        heap_percent = self._get_jvm_heap_usage()
        rss_gb = self._get_rss_memory_gb()
        
        # Check if API is unresponsive
        if heap_percent is None and rss_gb is None:
            self.api_unresponsive_count += 1
            logger.warning(f"Logstash API unresponsive ({self.api_unresponsive_count}/{self.api_unresponsive_threshold})")
            if self.api_unresponsive_count >= self.api_unresponsive_threshold:
                self.is_healthy = False
                return f"Logstash API unresponsive for {self.api_unresponsive_count * 5}s"
            return None
        else:
            # Reset unresponsive counter and mark healthy if we get data
            self.api_unresponsive_count = 0
            self.is_healthy = True
        
        # Check JVM heap (still monitor but less critical)
        if heap_percent and heap_percent > self.heap_threshold_percent:
            if self.high_memory_start_time is None:
                self.high_memory_start_time = time.time()
                logger.warning(f"[TIMER START] High JVM heap at {heap_percent:.1f}% (threshold: {self.heap_threshold_percent}%)")
            else:
                duration = time.time() - self.high_memory_start_time
                if duration >= self.threshold_duration_seconds:
                    logger.warning(f"[TIMER EXPIRED] High JVM heap for {duration:.0f}s")
                    return f"JVM heap at {heap_percent:.1f}% for {duration:.0f}s"
        else:
            if self.high_memory_start_time is not None:
                logger.info(f"[TIMER RESET] JVM heap back to normal")
                self.high_memory_start_time = None
        
        # Check RSS memory - CRITICAL: Restart immediately at 1.3x heap to prevent stun
        if rss_gb and self.heap_max_gb:
            rss_critical_gb = self.heap_max_gb * self.rss_critical_multiplier
            
            if rss_gb > rss_critical_gb:
                # Immediate restart to prevent Logstash from getting stunned
                logger.warning(f"RSS memory at {rss_gb:.2f}GB > critical threshold {rss_critical_gb:.2f}GB ({self.rss_critical_multiplier}x heap) - preventing stun")
                return f"RSS memory at {rss_gb:.2f}GB exceeds critical threshold {rss_critical_gb:.2f}GB ({self.rss_critical_multiplier}x heap - preventing stunned state)"
            else:
                heap_str = f"{heap_percent:.1f}%" if heap_percent is not None else "N/A"
                logger.debug(f"[MEMORY] Heap: {heap_str}, RSS: {rss_gb:.2f}GB / {rss_critical_gb:.2f}GB")
        elif rss_gb and not self.heap_max_gb:
            logger.debug(f"[MEMORY] RSS check skipped - heap_max_gb not yet cached (RSS: {rss_gb:.2f}GB)")
        
        return None
    
    def _monitor_loop(self):
        """Main monitoring loop (runs in background thread)"""
        logger.info("Memory monitoring loop started")
        logger.debug("[MONITOR] Entering monitoring loop")
        
        # Wait for Logstash to start up before polling APIs
        logger.info("Waiting 30s for Logstash to start up before monitoring...")
        time.sleep(30)
        logger.info("Starting memory monitoring")
        
        loop_iteration = 0
        while self.should_run:
            loop_iteration += 1
            logger.debug(f"[MONITOR] Loop iteration {loop_iteration} starting")
            try:
                # Check if process is still running
                logger.debug("[MONITOR] Checking if process is alive")
                if not self.process or self.process.poll() is not None:
                    exit_code = self.process.returncode if self.process else None
                    logger.error(f"Logstash process died (exit code: {exit_code})")
                    logger.debug(f"[MONITOR] Process crash detected - process exists: {self.process is not None}, poll: {self.process.poll() if self.process else 'N/A'}")
                    
                    # Capture and log stderr/stdout to see why it crashed
                    if self.process:
                        try:
                            stdout, stderr = self.process.communicate(timeout=1)
                            if stderr:
                                stderr_text = stderr.decode('utf-8', errors='replace')
                                logger.error(f"Logstash stderr output:\n{stderr_text}")
                            if stdout:
                                stdout_text = stdout.decode('utf-8', errors='replace')
                                logger.info(f"Logstash stdout output:\n{stdout_text}")
                        except Exception as e:
                            logger.warning(f"Could not capture process output: {e}")
                    
                    # Restart on crash
                    self.restart_logstash(f"Process crash (exit code: {exit_code})")
                    continue
                else:
                    logger.debug(f"[MONITOR] Process is alive - PID: {self.process.pid}")
                
                # Check memory thresholds
                logger.debug("[MONITOR] Checking memory thresholds")
                restart_reason = self._check_memory_thresholds()
                if restart_reason:
                    logger.debug(f"[MONITOR] Memory threshold exceeded: {restart_reason}")
                    self.restart_logstash(restart_reason)
                    continue
                else:
                    logger.debug("[MONITOR] Memory thresholds OK")
                
                # Check pipeline mismatch - TEMPORARILY DISABLED
                # logger.debug("[MONITOR] Checking pipeline mismatch")
                # restart_reason = self._check_pipeline_mismatch()
                # if restart_reason:
                #     logger.debug(f"[MONITOR] Pipeline mismatch detected: {restart_reason}")
                #     self.restart_logstash(restart_reason)
                # else:
                #     logger.debug("[MONITOR] Pipeline mismatch check OK")
                
                # Sleep before next check
                logger.debug(f"[MONITOR] Loop iteration {loop_iteration} complete, sleeping 5s")
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                logger.debug(f"[MONITOR] Exception in loop iteration {loop_iteration}", exc_info=True)
                logger.debug("[MONITOR] Sleeping 5s after error")
                time.sleep(5)
        
        logger.info("Memory monitoring loop stopped")
        logger.debug(f"[MONITOR] Exited monitoring loop after {loop_iteration} iterations")
    
    def shutdown(self):
        """Shutdown the supervisor"""
        logger.info("Shutting down LogstashSupervisor...")
        logger.debug("[SHUTDOWN] Setting should_run=False")
        self.should_run = False
        
        if self.monitor_thread:
            logger.debug(f"[SHUTDOWN] Waiting for monitor thread to stop (timeout=5s)")
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                logger.warning("[SHUTDOWN] Monitor thread did not stop within timeout")
            else:
                logger.debug("[SHUTDOWN] Monitor thread stopped")
        
        logger.debug("[SHUTDOWN] Stopping Logstash")
        self.stop_logstash(graceful=True)
        logger.info("LogstashSupervisor shutdown complete")
        logger.debug("[SHUTDOWN] Shutdown complete")


# Global supervisor instance
_supervisor: Optional[LogstashSupervisor] = None

def get_supervisor(config: dict = None) -> LogstashSupervisor:
    """Get or create the global supervisor instance"""
    global _supervisor
    if _supervisor is None:
        _supervisor = LogstashSupervisor(config=config)
    return _supervisor

def start_supervised_logstash(config: dict = None):
    """Start Logstash under supervision"""
    supervisor = get_supervisor(config=config)
    supervisor.start_logstash()

def trigger_restart(reason: str = "Manual restart"):
    """Trigger a Logstash restart from external code (e.g., when simulation POST fails)"""
    supervisor = get_supervisor()
    supervisor.restart_logstash(reason)

def shutdown_supervisor():
    """Shutdown the supervisor"""
    if _supervisor:
        _supervisor.shutdown()
