#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Template filters for SNMP display names."""

from django import template

from Common.formatters import format_display_name as _format_display_name

register = template.Library()


@register.filter(name='display_name')
def display_name(value):
    """Turn a slug such as ``dell_x1026`` into a label such as ``Dell X1026``."""
    return _format_display_name(value)
