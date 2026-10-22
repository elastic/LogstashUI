import pytest

from PipelineManager.editor_views import _load_plugin_data


ALLOWED_MODES = {"No", "value", "key", "both", "first"}
PLUGIN_SECTIONS = ("input", "filter", "output", "codec")


@pytest.fixture(scope="module")
def plugin_data():
    return _load_plugin_data()


def test_every_option_has_a_valid_field_reference_mode(plugin_data):
    """Every plugin option carries a field_reference flag the editor understands."""
    invalid = [
        f"{section}/{plugin}/{option}: {info.get('field_reference')!r}"
        for section in PLUGIN_SECTIONS
        for plugin, plugin_info in plugin_data[section].items()
        for option, info in plugin_info.get("options", {}).items()
        if info.get("field_reference") not in ALLOWED_MODES
    ]
    assert not invalid


@pytest.mark.parametrize(
    "section, plugin, option, expected",
    [
        ("filter", "mutate", "rename", "both"),
        ("filter", "mutate", "convert", "key"),
        ("filter", "date", "match", "first"),
        ("filter", "json", "target", "value"),
        ("filter", "grok", "match", "key"),
        ("filter", "translate", "dictionary", "No"),
        ("filter", "kv", "include_keys", "No"),
        ("input", "elasticsearch", "target", "value"),
        ("codec", "json", "target", "value"),
    ],
)
def test_field_reference_spot_checks(plugin_data, section, plugin, option, expected):
    """Known options are flagged with the expected field_reference mode."""
    assert plugin_data[section][plugin]["options"][option]["field_reference"] == expected


def test_common_filter_options_are_flagged(plugin_data):
    """add_field keys and remove_field values are field references on every filter."""
    for plugin, plugin_info in plugin_data["filter"].items():
        options = plugin_info["options"]
        if "add_field" in options:
            assert options["add_field"]["field_reference"] == "key", plugin
        if "remove_field" in options:
            assert options["remove_field"]["field_reference"] == "value", plugin
