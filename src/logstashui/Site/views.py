#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Site home, liveness probe, and Docker Hub update-check helpers."""

from django.core.cache import cache
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render

from packaging import version

import requests
import threading
import logging

logger = logging.getLogger(__name__)


def health_check(request):
    """Return 200 if the process is up.

    Used by container orchestrators. Does not check Elasticsearch or the DB.

    Returns:
        JsonResponse ``{"status": "healthy", "service": "logstashui"}``.
    """
    return JsonResponse({
        'status': 'healthy',
        'service': 'logstashui'
    })

def Home(request):
    """Render the product home page with app info and links."""
    return render(request, "home.html")



########################################
#### Version checker for our navigation
########################################
DOCKER_HUB_API = "https://hub.docker.com/v2/repositories/codyjackson032/logstashui/tags"
CACHE_KEY = "logstashui_latest_version"
CACHE_LOCK_KEY = "logstashui_version_fetch_lock"
CACHE_TIMEOUT = 60 * 60 * 6
LOCK_TIMEOUT = 30


def parse_version_tag(tag_name):
    """Parse a Docker tag into a packaging version.

    Args:
        tag_name: Tag string, with or without a leading ``v``.

    Returns:
        A ``packaging.version.Version``, or ``None`` if the tag is not
        a semantic version.
    """
    try:
        tag_name = tag_name.strip()
        if tag_name.startswith('v'):
            tag_name = tag_name[1:]
        return version.parse(tag_name)
    except Exception:
        return None


def fetch_latest_version_from_docker_hub():
    """Return the newest non-prerelease tag from the LogstashUI Docker Hub repo.

    Returns:
        Version string without a leading ``v``, or ``None`` on failure.
    """
    logger.debug("Fetching latest version from Docker Hub API")
    try:
        response = requests.get(DOCKER_HUB_API, timeout=5, params={"page_size": 100})
        response.raise_for_status()
        data = response.json()

        results = data.get('results', [])
        if not results:
            logger.warning("No tags found in Docker Hub API response")
            return None

        valid_versions = []
        for tag_info in results:
            tag_name = tag_info.get('name', '')
            parsed = parse_version_tag(tag_name)
            if parsed and not parsed.is_prerelease:
                valid_versions.append((parsed, tag_name))

        if not valid_versions:
            logger.warning("No valid semantic versions found in Docker Hub tags")
            return None

        valid_versions.sort(reverse=True, key=lambda x: x[0])
        latest_tag = valid_versions[0][1]

        if latest_tag.startswith('v'):
            latest_tag = latest_tag[1:]

        logger.debug(f"Successfully fetched latest version: {latest_tag}")
        return latest_tag

    except requests.exceptions.Timeout:
        logger.warning("Docker Hub API request timed out after 5 seconds")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch latest version from Docker Hub: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching version from Docker Hub: {e}", exc_info=True)
        return None


def update_latest_version_cache():
    """Refresh the cached latest version in a background thread.

    Always releases the fetch lock, even when Docker Hub fails.
    """
    try:
        latest = fetch_latest_version_from_docker_hub()
        if latest:
            cache.set(CACHE_KEY, latest, CACHE_TIMEOUT)
            logger.info(f"Updated latest version cache: {latest}")
        else:
            logger.warning("Failed to update version cache - no version retrieved")
    finally:
        # Always release the lock, even if fetch failed
        cache.delete(CACHE_LOCK_KEY)
        logger.debug("Released version fetch lock")


def get_latest_version():
    """Return the cached latest version, or start a background fetch.

    Uses ``cache.add`` as a lock so only one thread hits Docker Hub
    under concurrent cache misses.

    Returns:
        Cached version string, or ``None`` on a cold cache.
    """
    cached_version = cache.get(CACHE_KEY)

    if cached_version is None:
        logger.debug("Version cache miss - attempting to fetch latest version")
        # Try to acquire lock using cache.add (atomic operation)
        # Returns True only if key didn't exist (first thread wins)
        lock_acquired = cache.add(CACHE_LOCK_KEY, "locked", LOCK_TIMEOUT)
        
        if lock_acquired:
            logger.debug("Acquired version fetch lock - spawning background update thread")
            # This thread won the race - spawn background update
            thread = threading.Thread(target=update_latest_version_cache, daemon=True)
            thread.start()
        else:
            logger.debug("Version fetch already in progress by another thread")
    else:
        logger.debug(f"Version cache hit: {cached_version}")

    return cached_version


def check_for_update():
    """Compare the running version to the cached Docker Hub latest.

    Returns:
        Dict with ``current_version``, ``latest_version``,
        ``update_available``, and ``release_url`` when an update exists;
        otherwise ``None``.
    """
    current_version_str = getattr(settings, '__VERSION__', None)
    if not current_version_str:
        logger.warning("Current version not found in settings")
        return None

    latest_version_str = get_latest_version()
    if not latest_version_str:
        logger.debug("Latest version not available from cache")
        return None

    try:
        current = version.parse(current_version_str)
        latest = version.parse(latest_version_str)

        if latest > current:
            logger.info(f"Update available: {current_version_str} -> {latest_version_str}")
            return {
                'current_version': current_version_str,
                'latest_version': latest_version_str,
                'update_available': True,
                'release_url': f'https://github.com/elastic/LogstashUI/releases/tag/v{latest_version_str}'
            }
        else:
            logger.debug(f"Running latest version: {current_version_str}")
    except Exception as e:
        logger.error(f"Error comparing versions (current: {current_version_str}, latest: {latest_version_str}): {e}", exc_info=True)

    return None
