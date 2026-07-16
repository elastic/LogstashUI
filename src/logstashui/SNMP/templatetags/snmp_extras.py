#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django import template

from Common.formatters import format_display_name as _format_display_name

register = template.Library()


@register.filter(name='display_name')
def display_name(value):
    """
    Template filter that converts a slug-style device template/profile name
    (e.g. 'dell_x1026') into a human-friendly label (e.g. 'Dell X1026').
    """
    return _format_display_name(value)
