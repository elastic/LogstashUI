"""
Logstash API SDK

Provides a clean interface to interact with the Logstash Node Stats API.
This is more reliable than parsing logs for detecting pipeline state.

API Documentation: https://www.elastic.co/docs/api/doc/logstash/operation/operation-nodestatspipeline
"""

import logging
from typing import Dict, Any, Optional, List
import httpx
import time


logger = logging.getLogger(__name__)

# Logstash API configuration
LOGSTASH_API_HOST = "localhost"
LOGSTASH_API_PORT = 9600
LOGSTASH_API_BASE_URL = f"http://{LOGSTASH_API_HOST}:{LOGSTASH_API_PORT}"


class LogstashAPIError(Exception):
    """Base exception for Logstash API errors"""
    pass


class PipelineNotFoundError(LogstashAPIError):
    """Raised when a pipeline is not found"""
    pass


class LogstashAPI:
    """
    SDK for interacting with the Logstash Node Stats API.
    
    This provides methods to query pipeline statistics, detect pipeline state,
    and monitor pipeline health without relying on log parsing.
    """
    
    def __init__(self, base_url: str = LOGSTASH_API_BASE_URL, timeout: float = 5.0):
        """
        Initialize the Logstash API client.
        
        Args:
            base_url: Base URL for the Logstash API (default: http://localhost:9600)
            timeout: Request timeout in seconds (default: 5.0)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
    
    def close(self):
        """Close the HTTP client"""
        self.client.close()
    
    def get_node_info(self) -> Dict[str, Any]:
        """
        Get general node information.
        
        Returns:
            Dict containing node information (version, host, etc.)
        
        Raises:
            LogstashAPIError: If the request fails
        """
        try:
            response = self.client.get(f"{self.base_url}/")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise LogstashAPIError(f"Failed to get node info: {e}")
    
    def get_all_pipeline_stats(self) -> Dict[str, Any]:
        """
        Get statistics for all pipelines.
        
        Returns:
            Dict containing stats for all pipelines
        
        Raises:
            LogstashAPIError: If the request fails
        """
        try:
            response = self.client.get(f"{self.base_url}/_node/stats/pipelines")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise LogstashAPIError(f"Failed to get pipeline stats: {e}")
    
    def get_pipeline_stats(self, pipeline_name: str) -> Dict[str, Any]:
        """
        Get statistics for a specific pipeline.
        
        Args:
            pipeline_name: Name of the pipeline
        
        Returns:
            Dict containing pipeline statistics
        
        Raises:
            PipelineNotFoundError: If the pipeline doesn't exist
            LogstashAPIError: If the request fails
        """
        try:
            response = self.client.get(f"{self.base_url}/_node/stats/pipelines/{pipeline_name}")
            
            if response.status_code == 404:
                raise PipelineNotFoundError(f"Pipeline '{pipeline_name}' not found")
            
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                raise PipelineNotFoundError(f"Pipeline '{pipeline_name}' not found")
            raise LogstashAPIError(f"Failed to get pipeline stats for '{pipeline_name}': {e}")
    
    def list_pipelines(self) -> List[str]:
        """
        Get a list of all pipeline names currently loaded in Logstash.
        
        Returns:
            List of pipeline names
        
        Raises:
            LogstashAPIError: If the request fails
        """
        try:
            stats = self.get_all_pipeline_stats()
            pipelines = stats.get('pipelines', {})
            return list(pipelines.keys())
        except LogstashAPIError:
            raise
    
    def is_pipeline_running(self, pipeline_name: str) -> bool:
        """
        Check if a pipeline is currently running.
        
        A pipeline is considered "running" if:
        1. It exists in the API response
        2. It has processed at least one event OR has active workers
        
        Args:
            pipeline_name: Name of the pipeline to check
        
        Returns:
            True if the pipeline is running, False otherwise
        """
        try:
            stats = self.get_pipeline_stats(pipeline_name)
            
            # Extract pipeline data
            pipeline_data = stats.get('pipelines', {}).get(pipeline_name, {})
            
            if not pipeline_data:
                return False
            
            # Check if pipeline has events (indicates it's active)
            events = pipeline_data.get('events', {})
            events_in = events.get('in', 0)
            events_out = events.get('out', 0)
            
            # Pipeline is running if it exists and has processed events
            # OR if it has workers configured (even if no events yet)
            has_events = events_in > 0 or events_out > 0
            
            # Also check if reloads section exists (indicates pipeline is loaded)
            reloads = pipeline_data.get('reloads', {})
            has_reloads_data = reloads is not None
            
            return has_events or has_reloads_data
            
        except PipelineNotFoundError:
            return False
        except LogstashAPIError as e:
            logger.error(f"Error checking if pipeline '{pipeline_name}' is running: {e}")
            return False
    
    def get_pipeline_event_counts(self, pipeline_name: str) -> Dict[str, int]:
        """
        Get event counts for a pipeline.
        
        Args:
            pipeline_name: Name of the pipeline
        
        Returns:
            Dict with keys: 'in', 'filtered', 'out', 'duration_in_millis', 'queue_push_duration_in_millis'
        
        Raises:
            PipelineNotFoundError: If the pipeline doesn't exist
            LogstashAPIError: If the request fails
        """
        try:
            stats = self.get_pipeline_stats(pipeline_name)
            pipeline_data = stats.get('pipelines', {}).get(pipeline_name, {})
            events = pipeline_data.get('events', {})
            
            return {
                'in': events.get('in', 0),
                'filtered': events.get('filtered', 0),
                'out': events.get('out', 0),
                'duration_in_millis': events.get('duration_in_millis', 0),
                'queue_push_duration_in_millis': events.get('queue_push_duration_in_millis', 0)
            }
        except (PipelineNotFoundError, LogstashAPIError):
            raise
    
    def wait_for_pipeline_activity(
        self, 
        pipeline_name: str, 
        initial_event_count: Optional[int] = None,
        timeout: float = 10.0
    ) -> bool:
        """
        Wait for a pipeline to show activity (event count increase).
        
        This is useful for detecting when a newly created pipeline has started processing.
        
        Args:
            pipeline_name: Name of the pipeline
            initial_event_count: Expected initial event count (if None, will fetch current count)
            timeout: Maximum time to wait in seconds
        
        Returns:
            True if activity detected, False if timeout
        """
        start_time = time.time()
        
        # Get initial count if not provided
        if initial_event_count is None:
            try:
                counts = self.get_pipeline_event_counts(pipeline_name)
                initial_event_count = counts['in']
            except PipelineNotFoundError:
                initial_event_count = 0
        
        while time.time() - start_time < timeout:
            try:
                counts = self.get_pipeline_event_counts(pipeline_name)
                current_count = counts['in']
                
                if current_count > initial_event_count:
                    logger.info(f"Pipeline '{pipeline_name}' activity detected: {current_count} events")
                    return True
                    
            except PipelineNotFoundError:
                pass
            
            time.sleep(0.5)
        
        return False
    
    def detect_pipeline_state(self, pipeline_name: str) -> str:
        """
        Detect the current state of a pipeline.
        
        Args:
            pipeline_name: Name of the pipeline
        
        Returns:
            One of: 'running', 'idle', 'failed', 'not_found'
            - 'running': Pipeline exists and has processed events
            - 'idle': Pipeline exists but hasn't processed events yet (successfully loaded)
            - 'failed': Pipeline exists but failed to load (more failures than successes)
            - 'not_found': Pipeline doesn't exist in Logstash
        """
        try:
            stats = self.get_pipeline_stats(pipeline_name)
            pipelines_dict = stats.get('pipelines')
            
            # If pipelines key is missing or None, pipeline doesn't exist
            if pipelines_dict is None:
                logger.warning(f"Pipeline '{pipeline_name}' - API response missing 'pipelines' key")
                return 'not_found'
            
            pipeline_data = pipelines_dict.get(pipeline_name)
            
            # If pipeline_name is not in the response at all, it doesn't exist
            if pipeline_data is None:
                logger.warning(f"Pipeline '{pipeline_name}' - not found in pipelines dict")
                return 'not_found'
            
            # Check if pipeline_data is a dict (valid structure)
            if not isinstance(pipeline_data, dict):
                logger.warning(f"Pipeline '{pipeline_name}' - pipeline_data is not a dict: {type(pipeline_data)}")
                return 'not_found'
            
            # Debug: Log the full pipeline_data structure to understand what we're getting
            logger.debug(f"Pipeline '{pipeline_name}' - pipeline_data keys: {list(pipeline_data.keys())}")
            
            # Check reloads first to determine actual state
            # Reloads tell us if Logstash has attempted to load the pipeline
            reloads = pipeline_data.get('reloads')
            
            # If reloads is None, pipeline is still being registered by Logstash
            # This is normal for newly created pipelines - they appear in API before initialization
            if reloads is None:
                logger.debug(f"Pipeline '{pipeline_name}' - no 'reloads' structure yet (still registering)")
                return 'not_found'
            
            if not isinstance(reloads, dict):
                logger.warning(f"Pipeline '{pipeline_name}' - 'reloads' is not a dict: {type(reloads)}")
                return 'failed'
            
            reload_successes = reloads.get('successes', 0)
            reload_failures = reloads.get('failures', 0)
            
            # NOTE: We do NOT check absolute failure counts here because reload counters
            # are cumulative and persist across pipeline deletions in Logstash.
            # The verification logic in slots.py tracks baseline counters to detect NEW failures.
            # Here we only check if the pipeline has successfully initialized.
            
            # Check events structure to determine if pipeline has started
            # IMPORTANT: Logstash does NOT increment reload_successes for initial pipeline load
            # It only increments for subsequent reloads (config changes)
            # So we need to check if the pipeline has a valid events structure
            events = pipeline_data.get('events')
            
            if events is None:
                # No events structure yet - pipeline is still initializing
                logger.debug(f"Pipeline '{pipeline_name}' - no events structure yet (initializing)")
                return 'not_found'
            
            if not isinstance(events, dict):
                logger.warning(f"Pipeline '{pipeline_name}' - 'events' is not a dict: {type(events)}")
                return 'failed'
            
            # If events structure exists and has valid data, pipeline has started successfully
            # Check for required event fields that indicate pipeline is running
            events_in = events.get('in', 0)
            events_filtered = events.get('filtered', 0)
            events_out = events.get('out', 0)
            
            # Log the actual values we're seeing
            logger.info(f"Pipeline '{pipeline_name}' - events(in={events_in}, filtered={events_filtered}, out={events_out}), reloads(successes={reload_successes}, failures={reload_failures})")
            
            # If events structure has the required fields (even if all are 0), pipeline is loaded
            # The presence of these fields means Logstash has initialized the pipeline
            if 'in' in events or 'filtered' in events or 'out' in events:
                if events_in > 0:
                    return 'running'
                else:
                    logger.info(f"Pipeline '{pipeline_name}' - successfully loaded and idle")
                    return 'idle'
            
            # Events structure exists but doesn't have expected fields - still initializing
            logger.debug(f"Pipeline '{pipeline_name}' - events structure incomplete, still initializing")
            return 'not_found'
                
        except PipelineNotFoundError:
            return 'not_found'
        except LogstashAPIError as e:
            logger.error(f"Error detecting state for pipeline '{pipeline_name}': {e}")
            return 'not_found'
        except Exception as e:
            logger.error(f"Unexpected error detecting state for pipeline '{pipeline_name}': {e}")
            return 'failed'
    
    def get_pipeline_uptime(self, pipeline_name: str) -> Optional[float]:
        """
        Get the uptime of a pipeline in seconds.
        
        Args:
            pipeline_name: Name of the pipeline
        
        Returns:
            Uptime in seconds, or None if not available
        """
        try:
            stats = self.get_pipeline_stats(pipeline_name)
            pipeline_data = stats.get('pipelines', {}).get(pipeline_name, {})
            
            # Uptime can be calculated from duration_in_millis
            events = pipeline_data.get('events', {})
            duration_ms = events.get('duration_in_millis', 0)
            
            return duration_ms / 1000.0 if duration_ms > 0 else None
            
        except (PipelineNotFoundError, LogstashAPIError):
            return None
    
    def has_pipeline_attempted_load(self, pipeline_name: str) -> bool:
        """
        Check if a pipeline has attempted to load (has non-zero reload counters).
        
        This helps distinguish between:
        - Pipelines that are still initializing (reload counters are 0)
        - Pipelines that have attempted to load (reload counters > 0)
        
        Args:
            pipeline_name: Name of the pipeline
        
        Returns:
            True if pipeline has attempted to load, False otherwise
        """
        try:
            stats = self.get_pipeline_stats(pipeline_name)
            pipeline_data = stats.get('pipelines', {}).get(pipeline_name, {})
            
            if not pipeline_data:
                return False
            
            reloads = pipeline_data.get('reloads', {})
            if not isinstance(reloads, dict):
                return False
            
            reload_successes = reloads.get('successes', 0)
            reload_failures = reloads.get('failures', 0)
            
            # If either counter is non-zero, the pipeline has attempted to load
            return (reload_successes + reload_failures) > 0
            
        except (PipelineNotFoundError, LogstashAPIError):
            return False


# Convenience functions for common operations

def is_pipeline_loaded(pipeline_name: str, timeout: float = 5.0) -> bool:
    """
    Quick check if a pipeline is loaded in Logstash.
    
    Args:
        pipeline_name: Name of the pipeline
        timeout: Request timeout in seconds
    
    Returns:
        True if pipeline is loaded, False otherwise
    """
    with LogstashAPI(timeout=timeout) as api:
        return api.is_pipeline_running(pipeline_name)


def get_running_pipelines(timeout: float = 5.0) -> List[str]:
    """
    Get list of all running pipelines.
    
    Args:
        timeout: Request timeout in seconds
    
    Returns:
        List of pipeline names
    """
    with LogstashAPI(timeout=timeout) as api:
        return api.list_pipelines()


def wait_for_pipeline(pipeline_name: str, max_wait: float = 10.0, timeout: float = 5.0) -> bool:
    """
    Wait for a pipeline to appear and start running.
    
    Args:
        pipeline_name: Name of the pipeline
        max_wait: Maximum time to wait in seconds
        timeout: Request timeout in seconds
    
    Returns:
        True if pipeline is running, False if timeout
    """
    start_time = time.time()
    
    with LogstashAPI(timeout=timeout) as api:
        while time.time() - start_time < max_wait:
            if api.is_pipeline_running(pipeline_name):
                return True
            time.sleep(0.5)
    
    return False
