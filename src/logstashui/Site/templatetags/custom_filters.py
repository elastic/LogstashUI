#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django import template
from django.conf import settings

register = template.Library()

@register.filter(name='format_number')
def format_number(num):
    """Format large numbers with K/M suffixes"""
    try:
        num = float(num)
        if num >= 1000000:
            return f"{num / 1000000:.1f}M"
        if num >= 1000:
            return f"{num / 1000:.1f}K"
        return str(int(num))
    except (ValueError, TypeError):
        return num

@register.simple_tag
def app_version():
    """Get the application version from settings"""
    return getattr(settings, '__VERSION__', 'unknown')
