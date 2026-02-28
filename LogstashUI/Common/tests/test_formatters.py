import pytest
from Common.formatters import (
    _safe_get_numeric,
    _safe_extract_value,
    _format_uptime
)


class TestSafeGetNumeric:
    """Test _safe_get_numeric function with edge cases"""

    def test_integer_value(self):
        """Test integer value is returned as-is"""
        assert _safe_get_numeric(42) == 42
        assert isinstance(_safe_get_numeric(42), int)

    def test_float_value(self):
        """Test float value is returned as-is"""
        assert _safe_get_numeric(3.14) == 3.14
        assert isinstance(_safe_get_numeric(3.14), float)

    def test_string_integer(self):
        """Test string integer is converted to int"""
        assert _safe_get_numeric("123") == 123
        assert isinstance(_safe_get_numeric("123"), int)

    def test_string_float(self):
        """Test string float is converted to float"""
        assert _safe_get_numeric("3.14") == 3.14
        assert isinstance(_safe_get_numeric("3.14"), float)

    def test_none_returns_default(self):
        """Test None returns default value"""
        assert _safe_get_numeric(None) == 0
        assert _safe_get_numeric(None, default=100) == 100

    def test_empty_list_returns_default(self):
        """Test empty list returns default value"""
        assert _safe_get_numeric([]) == 0
        assert _safe_get_numeric([], default=50) == 50

    def test_list_with_integer(self):
        """Test list with integer returns first element"""
        assert _safe_get_numeric([42]) == 42
        assert _safe_get_numeric([42, 100]) == 42

    def test_list_with_float(self):
        """Test list with float returns first element"""
        assert _safe_get_numeric([3.14]) == 3.14
        assert _safe_get_numeric([3.14, 2.71]) == 3.14

    def test_list_with_string_number(self):
        """Test list with string number converts first element"""
        assert _safe_get_numeric(["123"]) == 123
        assert _safe_get_numeric(["3.14"]) == 3.14

    def test_invalid_string_returns_default(self):
        """Test invalid string returns default value"""
        assert _safe_get_numeric("not a number") == 0
        assert _safe_get_numeric("abc", default=99) == 99

    def test_list_with_invalid_string_returns_default(self):
        """Test list with invalid string returns default"""
        assert _safe_get_numeric(["invalid"]) == 0
        assert _safe_get_numeric(["invalid"], default=77) == 77

    def test_boolean_value(self):
        """Test boolean values (True=1, False=0)"""
        assert _safe_get_numeric(True) == 1
        assert _safe_get_numeric(False) == 0

    def test_zero_value(self):
        """Test zero is returned correctly"""
        assert _safe_get_numeric(0) == 0
        assert _safe_get_numeric("0") == 0
        assert _safe_get_numeric([0]) == 0

    def test_negative_numbers(self):
        """Test negative numbers are handled correctly"""
        assert _safe_get_numeric(-42) == -42
        assert _safe_get_numeric("-42") == -42
        assert _safe_get_numeric([-3.14]) == -3.14

    def test_custom_default_value(self):
        """Test custom default values work correctly"""
        assert _safe_get_numeric(None, default=-1) == -1
        assert _safe_get_numeric([], default=999) == 999
        assert _safe_get_numeric("invalid", default=42) == 42

    def test_list_with_none_returns_default(self):
        """Test list containing None returns default"""
        assert _safe_get_numeric([None]) == 0
        assert _safe_get_numeric([None], default=10) == 10

    def test_scientific_notation(self):
        """Test scientific notation strings - not supported, returns default"""
        # The function uses '.' check for float detection, so "1e3" is treated as invalid
        assert _safe_get_numeric("1e3") == 0
        # "1.5e2" has a period so it tries float() which works
        assert _safe_get_numeric("1.5e2") == 150.0

    def test_whitespace_in_string(self):
        """Test strings with whitespace"""
        assert _safe_get_numeric(" 123 ") == 123
        assert _safe_get_numeric(" 3.14 ") == 3.14

    def test_dict_returns_default(self):
        """Test dict returns default value"""
        assert _safe_get_numeric({"value": 123}) == 0
        assert _safe_get_numeric({"value": 123}, default=5) == 5


class TestSafeExtractValue:
    """Test _safe_extract_value function with edge cases"""

    def test_simple_value(self):
        """Test simple values are returned as-is"""
        assert _safe_extract_value("test") == "test"
        assert _safe_extract_value(123) == 123
        assert _safe_extract_value(3.14) == 3.14

    def test_none_returns_default(self):
        """Test None returns default value"""
        assert _safe_extract_value(None) == 0
        assert _safe_extract_value(None, default="default") == "default"

    def test_empty_list_returns_default(self):
        """Test empty list returns default value"""
        assert _safe_extract_value([]) == 0
        assert _safe_extract_value([], default="empty") == "empty"

    def test_list_with_value(self):
        """Test list with value returns first element"""
        assert _safe_extract_value(["test"]) == "test"
        assert _safe_extract_value([123]) == 123
        assert _safe_extract_value(["first", "second"]) == "first"

    def test_list_with_none_returns_default(self):
        """Test list with None values returns default"""
        assert _safe_extract_value([None]) == 0
        assert _safe_extract_value([None, None]) == 0
        assert _safe_extract_value([None], default="none") == "none"

    def test_list_with_empty_string_returns_default(self):
        """Test list with empty strings returns default"""
        assert _safe_extract_value([""]) == 0
        assert _safe_extract_value(["", ""]) == 0
        assert _safe_extract_value([""], default="empty") == "empty"

    def test_list_with_mixed_none_and_empty(self):
        """Test list with mix of None and empty strings returns default"""
        assert _safe_extract_value([None, "", None]) == 0
        assert _safe_extract_value(["", None, ""], default=99) == 99

    def test_list_with_valid_after_invalid(self):
        """Test list returns first non-null, non-empty value"""
        assert _safe_extract_value([None, "valid"]) == "valid"
        assert _safe_extract_value(["", "valid"]) == "valid"
        assert _safe_extract_value([None, "", "valid"]) == "valid"

    def test_list_with_zero(self):
        """Test list with zero value (zero is valid, not empty)"""
        assert _safe_extract_value([0]) == 0
        assert _safe_extract_value([None, 0]) == 0

    def test_list_with_false(self):
        """Test list with False value (False is valid, not empty)"""
        assert _safe_extract_value([False]) is False
        assert _safe_extract_value([None, False]) is False

    def test_custom_default_value(self):
        """Test custom default values"""
        assert _safe_extract_value(None, default="custom") == "custom"
        assert _safe_extract_value([], default=999) == 999

    def test_dict_value(self):
        """Test dict values are returned as-is"""
        test_dict = {"key": "value"}
        assert _safe_extract_value(test_dict) == test_dict

    def test_boolean_values(self):
        """Test boolean values are returned correctly"""
        assert _safe_extract_value(True) is True
        assert _safe_extract_value(False) is False

    def test_list_with_whitespace_string(self):
        """Test list with whitespace-only string (treated as non-empty)"""
        assert _safe_extract_value([" "]) == " "
        assert _safe_extract_value(["  "]) == "  "


class TestFormatUptime:
    """Test _format_uptime function with edge cases"""

    def test_zero_milliseconds(self):
        """Test zero milliseconds"""
        assert _format_uptime(0) == "0s"

    def test_seconds_only(self):
        """Test uptime in seconds only"""
        assert _format_uptime(5000) == "5s"
        assert _format_uptime(59000) == "59s"

    def test_minutes_and_seconds(self):
        """Test uptime in minutes and seconds"""
        assert _format_uptime(60000) == "1m 0s"
        assert _format_uptime(90000) == "1m 30s"
        assert _format_uptime(3599000) == "59m 59s"

    def test_hours_and_minutes(self):
        """Test uptime in hours and minutes"""
        assert _format_uptime(3600000) == "1h 0m"
        assert _format_uptime(3660000) == "1h 1m"
        assert _format_uptime(7200000) == "2h 0m"
        assert _format_uptime(86399000) == "23h 59m"

    def test_days_and_hours(self):
        """Test uptime in days and hours"""
        assert _format_uptime(86400000) == "1d 0h"
        assert _format_uptime(90000000) == "1d 1h"
        assert _format_uptime(172800000) == "2d 0h"
        assert _format_uptime(176400000) == "2d 1h"

    def test_one_millisecond(self):
        """Test one millisecond rounds to 0 seconds"""
        assert _format_uptime(1) == "0s"

    def test_999_milliseconds(self):
        """Test 999 milliseconds rounds to 0 seconds"""
        assert _format_uptime(999) == "0s"

    def test_exactly_one_minute(self):
        """Test exactly one minute"""
        assert _format_uptime(60000) == "1m 0s"

    def test_exactly_one_hour(self):
        """Test exactly one hour"""
        assert _format_uptime(3600000) == "1h 0m"

    def test_exactly_one_day(self):
        """Test exactly one day"""
        assert _format_uptime(86400000) == "1d 0h"

    def test_large_uptime(self):
        """Test large uptime values"""
        # 30 days
        assert _format_uptime(2592000000) == "30d 0h"
        # 365 days
        assert _format_uptime(31536000000) == "365d 0h"

    def test_complex_uptime(self):
        """Test complex uptime with all components"""
        # 1 day, 2 hours, 3 minutes, 4 seconds, 500 milliseconds
        ms = (1 * 86400000) + (2 * 3600000) + (3 * 60000) + (4 * 1000) + 500
        assert _format_uptime(ms) == "1d 2h"

    def test_uptime_priority_days_over_hours(self):
        """Test that days format takes priority over hours"""
        # 1 day, 23 hours
        ms = (1 * 86400000) + (23 * 3600000)
        assert _format_uptime(ms) == "1d 23h"

    def test_uptime_priority_hours_over_minutes(self):
        """Test that hours format takes priority over minutes"""
        # 1 hour, 59 minutes
        ms = (1 * 3600000) + (59 * 60000)
        assert _format_uptime(ms) == "1h 59m"

    def test_uptime_priority_minutes_over_seconds(self):
        """Test that minutes format takes priority over seconds"""
        # 1 minute, 59 seconds
        ms = (1 * 60000) + (59 * 1000)
        assert _format_uptime(ms) == "1m 59s"

    def test_negative_uptime(self):
        """Test negative uptime (edge case, should handle gracefully)"""
        # Negative values will result in negative calculations
        result = _format_uptime(-1000)
        assert "s" in result

    def test_fractional_seconds(self):
        """Test that fractional seconds are truncated"""
        # 1500ms = 1.5 seconds, should show as 1s
        assert _format_uptime(1500) == "1s"
        # 2999ms = 2.999 seconds, should show as 2s
        assert _format_uptime(2999) == "2s"

    @pytest.mark.parametrize("milliseconds,expected", [
        (0, "0s"),
        (1000, "1s"),
        (60000, "1m 0s"),
        (3600000, "1h 0m"),
        (86400000, "1d 0h"),
        (90061000, "1d 1h"),  # 1 day, 1 hour, 1 minute, 1 second
        (5000, "5s"),
        (125000, "2m 5s"),
        (7325000, "2h 2m"),
        (90000000, "1d 1h"),
    ])
    def test_parametrized_uptime_formats(self, milliseconds, expected):
        """Test various uptime formats with parametrized inputs"""
        assert _format_uptime(milliseconds) == expected
