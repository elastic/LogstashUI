from django import template

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
