"""Agent guides: short Markdown how-tos for working with LogstashUI.

The text lives in ``docs/docs/logstashui/agent_guides/<topic>.md`` so it also
shows up in the in-app documentation. It is served by ``GET /api/guides/`` and
the ``guides_*`` MCP tools.

Examples:
    >>> 'simulation' in GUIDES
    True
    >>> read_guide('simulation').splitlines()[0]
    '# Simulating pipelines'
"""

import logging

from django.http import JsonResponse

from API.auth import api_require_auth
from Documentation.views import DOCS_DIR

logger = logging.getLogger(__name__)

GUIDES_DIR = DOCS_DIR / 'logstashui' / 'agent_guides'

#: ``{topic: one-line description}``; each topic has ``<topic>.md`` in GUIDES_DIR.
GUIDES = {
    'concepts': 'Vocabulary and objects: agent vs. CPM pipelines, policies, SNMP, and when '
                'each change goes live. Read first.',
    'pipeline-review': 'How to review a Logstash pipeline: build samples, simulate, and what to '
                       'check.',
    'simulation': 'Using pipelines_simulate: config sources, bulk events, detail levels, and '
                  'reading results.',
    'deploy': 'Changing and deploying agent pipelines, CPM pipelines, and SNMP with user '
              'confirmation.',
    'snmp': 'SNMP objects and how to add a device.',
    'troubleshooting': 'What each error status means, retry rules, and staying on the MCP '
                       'interface.',
}


def read_guide(topic):
    """Return the Markdown for ``topic``, or ``None`` if it is not available.

    Args:
        topic: A key of :data:`GUIDES`.

    Returns:
        str | None: The guide text; ``None`` for an unknown topic or a missing file.
    """
    if topic not in GUIDES:
        return None
    try:
        return (GUIDES_DIR / f'{topic}.md').read_text(encoding='utf-8')
    except OSError as exc:
        logger.error("Agent guide '%s' is missing from %s: %s", topic, GUIDES_DIR, exc)
        return None


@api_require_auth
def guide_list(request):
    """List agent guides.

    GET /api/guides/
        Returns ``guides``: ``[{topic, description}]``. Any authenticated user.
    """
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    guides = [{'topic': t, 'description': d} for t, d in GUIDES.items()]
    return JsonResponse({'success': True, 'guides': guides, 'count': len(guides)})


@api_require_auth
def guide_detail(request, topic):
    """Return one agent guide as Markdown.

    GET /api/guides/{topic}/
        Returns ``topic``, ``description``, and ``content``. Any authenticated user.
    """
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    content = read_guide(topic)
    if content is None:
        error = (f"Guide '{topic}' is not installed on this server." if topic in GUIDES
                 else f"Unknown guide '{topic}'. Valid topics: {', '.join(GUIDES)}.")
        return JsonResponse({'success': False, 'error': error}, status=404)
    return JsonResponse(
        {'success': True, 'topic': topic, 'description': GUIDES[topic], 'content': content}
    )
