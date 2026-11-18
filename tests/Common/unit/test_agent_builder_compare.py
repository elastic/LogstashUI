#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.ai.agent_builder import RESOURCE_AGENT, RESOURCE_SKILL, AgentBuilder


DESIRED = {
    'id': 'snmp-profile-author',
    'name': 'SNMP Profile Author',
    'description': 'Authors profiles',
    'configuration': {'instructions': 'Do the thing', 'skill_ids': ['snmp-catalog'], 'tools': []},
}


def _current(**config):
    current = {k: v for k, v in DESIRED.items() if k != 'configuration'}
    current['configuration'] = {'instructions': 'Do the thing', **config}
    return current


def test_kibana_default_empty_keys_do_not_differ():
    current = _current(subagent_ids=[], skill_ids=['snmp-catalog'], tools=[])
    assert AgentBuilder._differs(DESIRED, current, RESOURCE_AGENT) is False


def test_write_only_keys_missing_from_response_do_not_differ():
    assert AgentBuilder._differs(DESIRED, _current(), RESOURCE_AGENT) is False


def test_changed_instructions_differ():
    current = _current(subagent_ids=[])
    current['configuration']['instructions'] = 'Old text'
    assert AgentBuilder._diff_fields(DESIRED, current, RESOURCE_AGENT) == ['configuration']


def test_non_empty_extra_key_differs():
    current = _current(subagent_ids=['other-agent'])
    assert AgentBuilder._differs(DESIRED, current, RESOURCE_AGENT) is True


def test_non_agent_resources_are_not_normalized():
    skill = {'id': 's', 'content': ''}
    assert AgentBuilder._normalize(skill, RESOURCE_SKILL) is skill
