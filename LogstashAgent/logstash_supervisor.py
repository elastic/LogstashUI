#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import subprocess
import threading
import time
import logging
import os
import signal
import psutil
from typing import Optional
from logstash_api import LogstashAPI
import slots

logger = logging.getLogger(__name__)

class LogstashSupervisor:
    """
    Supervises the Logstash process with automatic restart on:
    1. Process crash/OOM
    2. JVM heap usage > 90% for 30+ seconds
    3. RSS memory dynamically calculated based on heap size
    
    Currently always runs in simulation mode (supervised Logstash).
    TODO: Add detection for production vs simulation nodes in the future.
    """
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.should_run = True
        
        # TODO: In the future, detect if this is a simulation node vs production node
        # For now, always default to simulation mode (supervised Logstash with memory monitoring)
        # Production nodes would run Logstash without supervision
        self.simulation_mode = True
        
        # Memory thresholds
        self.heap_threshold_percent = 90.0
        self.threshold_duration_seconds = 30.0
        
        # RSS thresholds will be calculated dynamically based on JVM heap size
        # Watch threshold: RSS > 1.2x heap (wait 30s before restart)
        # Critical threshold: RSS > 1.75x heap (immediate restart)
        # (JVM overhead + off-heap memory + OS buffers)
        self.rss_watch_multiplier = 1.2
        self.rss_critical_multiplier = 1.75
        self.heap_max_gb: Optional[float] = None  # Will be fetched from Logstash API
        
        # Tracking
        self.high_memory_start_time: Optional[float] = None
        self.restart_count = 0
        self.api_unresponsive_count = 0
        self.api_unresponsive_threshold = 3  # Restart after 3 consecutive API failures
        
        logger.info(f"LogstashSupervisor initialized (simulation_mode={self.simulation_mode})")
    
    def start_logstash(self):
        """Start the Logstash process"""
        if self.process and self.process.poll() is not None:
            logger.warning("Logstash is already running")
            return
        
        logger.info("Starting Logstash process...")
        
        # Prepare environment - copy all environment variables
        env = os.environ.copy()
        env['LS_JAVA_OPTS'] = "-Dlog4j.configurationFile=/etc/logstash/log4j2.properties"
        
        # Ensure LOGSTASH_URL is available to Logstash
        # This is critical for http output plugin in simulate_end.conf and simulate_start.conf
        if 'LOGSTASH_URL' not in env:
            # Set default for standalone builds (works on Docker Desktop)
            env['LOGSTASH_URL'] = 'http://host.docker.internal:8080'
            logger.info(f"LOGSTASH_URL not set, using default: {env['LOGSTASH_URL']}")
        else:
            logger.info(f"LOGSTASH_URL: {env['LOGSTASH_URL']}")
        
        # Start Logstash
        self.process = subprocess.Popen(
            ['/usr/share/logstash/bin/logstash', '--path.settings', '/etc/logstash'],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Create new process group for clean shutdown
        )
        
        logger.info(f"Logstash started with PID {self.process.pid}")
        
        # Start monitoring thread if in simulation mode
        if self.simulation_mode and not self.monitor_thread:
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("Memory monitoring thread started")
    
    def stop_logstash(self, graceful=True):
        """Stop the Logstash process"""
        if not self.process:
            return
        
        logger.info(f"Stopping Logstash (PID {self.process.pid}, graceful={graceful})...")
        
        try:
            if graceful:
                # Send SIGTERM for graceful shutdown
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                
                # Wait up to 30 seconds for graceful shutdown
                try:
                    self.process.wait(timeout=30)
                    logger.info("Logstash stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("Graceful shutdown timed out, forcing kill")
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait()
            else:
                # Force kill
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                self.process.wait()
                logger.info("Logstash killed")
        except Exception as e:
            logger.error(f"Error stopping Logstash: {e}")
        
        self.process = None
    
    def restart_logstash(self, reason: str):
        """Restart Logstash with a given reason"""
        self.restart_count += 1
        logger.warning(f"Restarting Logstash (restart #{self.restart_count}): {reason}")
        
        # Evict all slots BEFORE stopping Logstash to prevent reloading crash-causing pipelines
        logger.info("Evicting all slots before restart to prevent reloading problematic pipelines...")
        try:
            slot_state = slots.get_slot_state()
            active_slots = [slot_id for slot_id, data in slot_state.items() if data]
            
            if active_slots:
                logger.info(f"Evicting {len(active_slots)} active slots: {active_slots}")
                for slot_id in active_slots:
                    try:
                        slots.release_slot(slot_id)
                        logger.info(f"Evicted slot {slot_id}")
                    except Exception as e:
                        logger.error(f"Error evicting slot {slot_id}: {e}")
            else:
                logger.info("No active slots to evict")
        except Exception as e:
            logger.error(f"Error during slot eviction: {e}")
        
        self.stop_logstash(graceful=True)
        
        # Brief pause to ensure clean shutdown
        time.sleep(2)
        
        self.start_logstash()
        
        # Reset memory tracking
        self.high_memory_start_time = None
    
    def _get_jvm_heap_usage(self) -> Optional[float]:
        """Get JVM heap usage percentage from Logstash API"""
        try:
            with LogstashAPI(timeout=2.0) as api:
                stats = api.get_node_stats()
                jvm = stats.get('jvm', {})
                mem = jvm.get('mem', {})
                heap_used = mem.get('heap_used_in_bytes', 0)
                heap_max = mem.get('heap_max_in_bytes', 1)
                
                # Cache heap_max_gb for RSS threshold calculation
                if heap_max > 0 and self.heap_max_gb is None:
                    self.heap_max_gb = heap_max / (1024 ** 3)
                    logger.info(f"JVM heap max detected: {self.heap_max_gb:.2f}GB")
                    logger.info(f"RSS watch threshold: {self.heap_max_gb * self.rss_watch_multiplier:.2f}GB (30s wait)")
                    logger.info(f"RSS critical threshold: {self.heap_max_gb * self.rss_critical_multiplier:.2f}GB (immediate restart)")
                
                if heap_max > 0:
                    return (heap_used / heap_max) * 100.0
        except Exception as e:
            logger.debug(f"Could not get JVM heap usage: {e}")
        
        return None
    
    def _get_rss_memory_gb(self) -> Optional[float]:
        """Get RSS memory usage in GB for Logstash process"""
        if not self.process or self.process.poll() is not None:
            return None
        
        try:
            proc = psutil.Process(self.process.pid)
            # Get memory for process and all children
            total_rss = proc.memory_info().rss
            for child in proc.children(recursive=True):
                try:
                    total_rss += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            return total_rss / (1024 ** 3)  # Convert bytes to GB
        except Exception as e:
            logger.debug(f"Could not get RSS memory: {e}")
        
        return None
    
    def _check_memory_thresholds(self) -> Optional[str]:
        """
        Check if memory thresholds are exceeded.
        Returns restart reason immediately if critical threshold exceeded,
        or after 30s if watch threshold exceeded.
        """
        heap_percent = self._get_jvm_heap_usage()
        rss_gb = self._get_rss_memory_gb()
        
        # Check if API is unresponsive
        if heap_percent is None and rss_gb is None:
            self.api_unresponsive_count += 1
            logger.warning(f"Logstash API unresponsive ({self.api_unresponsive_count}/{self.api_unresponsive_threshold})")
            if self.api_unresponsive_count >= self.api_unresponsive_threshold:
                return f"Logstash API unresponsive for {self.api_unresponsive_count * 5}s"
            return None
        else:
            # Reset unresponsive counter if we get data
            self.api_unresponsive_count = 0
        
        # Determine if we're in high memory state
        high_memory = False
        immediate_restart = False
        reason = None
        
        # Check JVM heap
        if heap_percent and heap_percent > self.heap_threshold_percent:
            high_memory = True
            reason = f"JVM heap at {heap_percent:.1f}% (threshold: {self.heap_threshold_percent}%)"
        
        # Check RSS memory
        if rss_gb and self.heap_max_gb:
            rss_watch_gb = self.heap_max_gb * self.rss_watch_multiplier
            rss_critical_gb = self.heap_max_gb * self.rss_critical_multiplier
            
            if rss_gb > rss_critical_gb:
                # Critical threshold - immediate restart
                immediate_restart = True
                reason = f"RSS memory at {rss_gb:.2f}GB > critical threshold {rss_critical_gb:.2f}GB"
            elif rss_gb > rss_watch_gb:
                # Watch threshold - wait 30s before restart
                high_memory = True
                reason = f"RSS memory at {rss_gb:.2f}GB > watch threshold {rss_watch_gb:.2f}GB"
        
        # Immediate restart for critical threshold
        if immediate_restart:
            logger.warning(f"Critical memory threshold exceeded: {reason}")
            self.high_memory_start_time = None  # Reset tracking
            return reason
        
        # Track high memory duration for watch threshold
        if high_memory:
            if self.high_memory_start_time is None:
                self.high_memory_start_time = time.time()
                logger.info(f"High memory detected: {reason}")
            else:
                duration = time.time() - self.high_memory_start_time
                if duration >= self.threshold_duration_seconds:
                    return f"{reason} for {duration:.0f}s"
        else:
            # Reset tracking if memory is back to normal
            if self.high_memory_start_time is not None:
                logger.info("Memory back to normal levels")
                self.high_memory_start_time = None
        
        return None
    
    def _monitor_loop(self):
        """Main monitoring loop (runs in background thread)"""
        logger.info("Memory monitoring loop started")
        
        while self.should_run:
            try:
                # Check if process is still running
                if not self.process or self.process.poll() is not None:
                    exit_code = self.process.returncode if self.process else None
                    logger.error(f"Logstash process died (exit code: {exit_code})")
                    
                    # Restart on crash
                    self.restart_logstash(f"Process crash (exit code: {exit_code})")
                    continue
                
                # Check memory thresholds
                restart_reason = self._check_memory_thresholds()
                if restart_reason:
                    self.restart_logstash(restart_reason)
                
                # Sleep before next check
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                time.sleep(5)
        
        logger.info("Memory monitoring loop stopped")
    
    def shutdown(self):
        """Shutdown the supervisor"""
        logger.info("Shutting down LogstashSupervisor...")
        self.should_run = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        self.stop_logstash(graceful=True)
        logger.info("LogstashSupervisor shutdown complete")


# Global supervisor instance
_supervisor: Optional[LogstashSupervisor] = None

def get_supervisor() -> LogstashSupervisor:
    """Get or create the global supervisor instance"""
    global _supervisor
    if _supervisor is None:
        _supervisor = LogstashSupervisor()
    return _supervisor

def start_supervised_logstash():
    """Start Logstash under supervision"""
    supervisor = get_supervisor()
    supervisor.start_logstash()

def shutdown_supervisor():
    """Shutdown the supervisor"""
    if _supervisor:
        _supervisor.shutdown()
