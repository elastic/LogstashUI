import pytest
from Common.validators import validate_pipeline_name


class TestValidatePipelineName:
    """Test validate_pipeline_name function with parametrized tests"""

    @pytest.mark.parametrize("pipeline_name,expected_valid", [
        ("valid_pipeline", True),
        ("ValidPipeline", True),
        ("_underscore_start", True),
        ("pipeline123", True),
        ("pipeline_with_dash-123", True),
        ("a", True),
        ("_", True),
        ("Pipeline_Name_123", True),
        ("my-pipeline-name", True),
        ("my_pipeline_name", True),
        ("ABC123_test-pipeline", True),
    ])
    def test_valid_pipeline_names(self, pipeline_name, expected_valid):
        """Test valid pipeline names"""
        is_valid, error_message = validate_pipeline_name(pipeline_name)
        assert is_valid == expected_valid
        assert error_message is None

    @pytest.mark.parametrize("pipeline_name,expected_error_fragment", [
        ("", "cannot be empty"),
        ("123pipeline", "must begin with a letter or underscore"),
        ("-pipeline", "must begin with a letter or underscore"),
        ("pipeline name", "must begin with a letter or underscore"),
        ("pipeline@name", "must begin with a letter or underscore"),
        ("pipeline.name", "must begin with a letter or underscore"),
        ("pipeline$name", "must begin with a letter or underscore"),
        ("pipeline#name", "must begin with a letter or underscore"),
        ("pipeline!name", "must begin with a letter or underscore"),
        ("pipeline*name", "must begin with a letter or underscore"),
        ("pipeline(name)", "must begin with a letter or underscore"),
        ("pipeline[name]", "must begin with a letter or underscore"),
        ("pipeline{name}", "must begin with a letter or underscore"),
        ("pipeline/name", "must begin with a letter or underscore"),
        ("pipeline\\name", "must begin with a letter or underscore"),
        ("pipeline:name", "must begin with a letter or underscore"),
        ("pipeline;name", "must begin with a letter or underscore"),
        ("pipeline,name", "must begin with a letter or underscore"),
        ("pipeline<name>", "must begin with a letter or underscore"),
        ("pipeline?name", "must begin with a letter or underscore"),
        ("pipeline|name", "must begin with a letter or underscore"),
        ("pipeline~name", "must begin with a letter or underscore"),
        ("pipeline`name", "must begin with a letter or underscore"),
        ("pipeline'name", "must begin with a letter or underscore"),
        ('pipeline"name', "must begin with a letter or underscore"),
    ])
    def test_invalid_pipeline_names(self, pipeline_name, expected_error_fragment):
        """Test invalid pipeline names"""
        is_valid, error_message = validate_pipeline_name(pipeline_name)
        assert is_valid is False
        assert error_message is not None
        assert expected_error_fragment in error_message.lower()

    def test_empty_string(self):
        """Test empty string returns specific error"""
        is_valid, error_message = validate_pipeline_name("")
        assert is_valid is False
        assert error_message == "Pipeline name cannot be empty"

    def test_none_value(self):
        """Test None value is treated as empty"""
        is_valid, error_message = validate_pipeline_name(None)
        assert is_valid is False
        assert error_message == "Pipeline name cannot be empty"

    def test_starts_with_number(self):
        """Test pipeline name starting with number is invalid"""
        is_valid, error_message = validate_pipeline_name("1pipeline")
        assert is_valid is False
        assert "must begin with a letter or underscore" in error_message
        assert "[1pipeline]" in error_message

    def test_starts_with_dash(self):
        """Test pipeline name starting with dash is invalid"""
        is_valid, error_message = validate_pipeline_name("-pipeline")
        assert is_valid is False
        assert "must begin with a letter or underscore" in error_message

    def test_contains_space(self):
        """Test pipeline name with spaces is invalid"""
        is_valid, error_message = validate_pipeline_name("my pipeline")
        assert is_valid is False
        assert "must begin with a letter or underscore" in error_message

    def test_contains_special_characters(self):
        """Test pipeline name with special characters is invalid"""
        is_valid, error_message = validate_pipeline_name("pipeline@test")
        assert is_valid is False
        assert "must begin with a letter or underscore" in error_message

    def test_valid_with_all_allowed_characters(self):
        """Test pipeline name with all allowed character types"""
        is_valid, error_message = validate_pipeline_name("aZ_09-")
        assert is_valid is True
        assert error_message is None

    def test_single_letter(self):
        """Test single letter is valid"""
        is_valid, error_message = validate_pipeline_name("a")
        assert is_valid is True
        assert error_message is None

    def test_single_underscore(self):
        """Test single underscore is valid"""
        is_valid, error_message = validate_pipeline_name("_")
        assert is_valid is True
        assert error_message is None

    def test_long_pipeline_name(self):
        """Test very long pipeline name is valid if format is correct"""
        long_name = "a" * 1000
        is_valid, error_message = validate_pipeline_name(long_name)
        assert is_valid is True
        assert error_message is None

    def test_error_message_includes_pipeline_name(self):
        """Test that error message includes the invalid pipeline name"""
        invalid_name = "123invalid"
        is_valid, error_message = validate_pipeline_name(invalid_name)
        assert is_valid is False
        assert invalid_name in error_message

    def test_unicode_characters_invalid(self):
        """Test that unicode characters are invalid"""
        is_valid, error_message = validate_pipeline_name("pipeline_中文")
        assert is_valid is False
        assert "must begin with a letter or underscore" in error_message

    def test_emoji_invalid(self):
        """Test that emoji characters are invalid"""
        is_valid, error_message = validate_pipeline_name("pipeline_🔥")
        assert is_valid is False
        assert "must begin with a letter or underscore" in error_message

    @pytest.mark.parametrize("valid_start", ["a", "Z", "_"])
    def test_valid_starting_characters(self, valid_start):
        """Test all valid starting characters"""
        is_valid, error_message = validate_pipeline_name(f"{valid_start}pipeline")
        assert is_valid is True
        assert error_message is None

    def test_consecutive_dashes_and_underscores(self):
        """Test pipeline name with consecutive dashes and underscores"""
        is_valid, error_message = validate_pipeline_name("pipeline__--__name")
        assert is_valid is True
        assert error_message is None

    def test_ends_with_dash(self):
        """Test pipeline name ending with dash is valid"""
        is_valid, error_message = validate_pipeline_name("pipeline-")
        assert is_valid is True
        assert error_message is None

    def test_ends_with_underscore(self):
        """Test pipeline name ending with underscore is valid"""
        is_valid, error_message = validate_pipeline_name("pipeline_")
        assert is_valid is True
        assert error_message is None

    def test_ends_with_number(self):
        """Test pipeline name ending with number is valid"""
        is_valid, error_message = validate_pipeline_name("pipeline123")
        assert is_valid is True
        assert error_message is None
