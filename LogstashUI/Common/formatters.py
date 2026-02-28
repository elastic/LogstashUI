

def _safe_get_numeric(data, default=0):
    """
    Safely extract a numeric value from data.
    Handles cases where data might be a list, None, or invalid.
    Returns default if value cannot be converted to a number.
    """
    if data is None:
        return default

    # If it's a list, try to get the first element
    if isinstance(data, list):
        if len(data) == 0:
            return default
        data = data[0]

    # Try to convert to the appropriate numeric type
    try:
        if isinstance(data, (int, float)):
            return data
        return float(data) if '.' in str(data) else int(data)
    except (ValueError, TypeError):
        return default


def _safe_extract_value(data, default=0):
    """
    Safely extract a value from pipeline data.
    Returns default if value is None, empty list, or invalid.
    """
    if data is None:
        return default
    if isinstance(data, list):
        # If it's an empty list or list with no valid values, return default
        if not data or all(v is None or v == '' for v in data):
            return default
        # If it's a list with values, return the first non-null value
        for v in data:
            if v is not None and v != '':
                return v
        return default
    return data


def _format_uptime(milliseconds):
    """Format uptime from milliseconds to human-readable string"""
    seconds = milliseconds // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        return f"{days}d {hours % 24}h"
    elif hours > 0:
        return f"{hours}h {minutes % 60}m"
    elif minutes > 0:
        return f"{minutes}m {seconds % 60}s"
    else:
        return f"{seconds}s"