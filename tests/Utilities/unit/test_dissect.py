import pytest

from Utilities.dissect import Dissector, DissectError, DissectFailure
from Utilities.views import parse_convert_datatype, simulate_dissect


class TestDissector:
    """Behaviour of the dissect parser, mostly taken from the Logstash dissect docs."""

    def test_syslog_with_append(self):
        pattern = "%{ts} %{+ts} %{+ts} %{src} %{prog}[%{pid}]: %{msg}"
        text = "Mar 16 00:01:25 evita postfix/smtpd[1713]: connect from camomile.cloud9.net[168.100.1.3]"
        assert Dissector(pattern).match(text) == {
            "ts": "Mar 16 00:01:25",
            "src": "evita",
            "prog": "postfix/smtpd",
            "pid": "1713",
            "msg": "connect from camomile.cloud9.net[168.100.1.3]",
        }

    def test_append_ordering(self):
        pattern = "%{+name/2} %{+name/4} %{+name/3} %{+name/1}"
        assert Dissector(pattern).match("john jacob jingleheimer schmidt") == {
            "name": "schmidt john jingleheimer jacob"
        }

    def test_append_separator(self):
        assert Dissector("%{a} %{+a} %{+a}", append_separator="-").match("1 2 3") == {"a": "1-2-3"}

    def test_right_padding(self):
        assert Dissector("%{ts->} %{level} %{msg}").match("12:00    INFO started up") == {
            "ts": "12:00",
            "level": "INFO",
            "msg": "started up",
        }

    @pytest.mark.parametrize("pattern,text,expected", [
        ("%{a} %{b} %{c}", "x  y", {"a": "x", "b": "", "c": "y"}),
        ("%{a} %{b}", "x ", {"a": "x", "b": ""}),
        ("%{a} %{b}", " y", {"a": "", "b": "y"}),
        ("%{a} %{+a} %{+a}", "x  z", {"a": "x  z"}),
    ])
    def test_empty_values_are_kept(self, pattern, text, expected):
        """Verified against Logstash: empty captures are set as "" and still joined when appended."""
        assert Dissector(pattern).match(text) == expected

    def test_skip_fields(self):
        assert Dissector("%{a} %{} %{?ignored} %{b}").match("1 2 3 4") == {"a": "1", "b": "4"}

    @pytest.mark.parametrize("pattern,text", [("%{*k}=%{&k}", "foo=bar"), ("%{?k}: %{&k}", "foo: bar")])
    def test_key_value_reference(self, pattern, text):
        assert Dissector(pattern).match(text) == {"foo": "bar"}

    def test_nested_field_reference(self):
        assert Dissector("%{[client][ip]} %{[client][port]} %{a.b}").match("1.2.3.4 80 x") == {
            "client": {"ip": "1.2.3.4", "port": "80"},
            "a.b": "x",
        }

    def test_literal_prefix_and_suffix(self):
        dissector = Dissector("[%{level}] %{msg}.")
        assert dissector.match("[WARN] disk low.") == {"level": "WARN", "msg": "disk low"}
        with pytest.raises(DissectFailure):
            dissector.match("WARN disk low.")

    def test_missing_delimiter_fails(self):
        with pytest.raises(DissectFailure, match="was not found"):
            Dissector("%{a} - %{b}").match("no dash here")

    def test_convert_datatype(self):
        dissector = Dissector("%{bytes} %{ms} %{bad}", convert_datatype={"bytes": "int", "ms": "float", "bad": "int"})
        assert dissector.match("512 1.5 nope") == {"bytes": 512, "ms": 1.5, "bad": "nope"}

    @pytest.mark.parametrize("pattern", [
        "no fields",
        "%{a}%{b}",
        "%{&missing}",
        "%{+}",
    ])
    def test_invalid_patterns(self, pattern):
        with pytest.raises(DissectError):
            Dissector(pattern)

    def test_invalid_datatype(self):
        with pytest.raises(DissectError):
            Dissector("%{a}", convert_datatype={"a": "bool"})


def test_parse_convert_datatype():
    assert parse_convert_datatype('bytes => int\n"ms" => "float"\n\n') == {"bytes": "int", "ms": "float"}
    with pytest.raises(DissectError):
        parse_convert_datatype("bytes => int extra")


@pytest.mark.django_db
class TestSimulateDissectView:
    """The HTMX simulate endpoint."""

    def _post(self, request_factory, **data):
        return simulate_dissect(request_factory.post('/Utilities/DissectDebugger/simulate/', data))

    def test_match_and_failure(self, request_factory):
        response = self._post(
            request_factory,
            sample_data="1.2.3.4 GET\nbroken",
            dissect_pattern="%{ip} %{verb}",
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "1 matched" in content and "1 failed" in content
        assert "&quot;verb&quot;: &quot;GET&quot;" in content
        assert "_dissectfailure" in content

    def test_compilation_error(self, request_factory):
        content = self._post(request_factory, sample_data="x", dissect_pattern="%{a}%{b}").content.decode()
        assert "Pattern compilation error" in content

    def test_multiline_mode(self, request_factory):
        content = self._post(
            request_factory, sample_data="a\nb", dissect_pattern="%{msg}", multiline_mode="true"
        ).content.decode()
        assert "1 matched" in content

    def test_escapes_html(self, request_factory):
        content = self._post(request_factory, sample_data="<script>x</script>", dissect_pattern="%{m}").content.decode()
        assert "<script>" not in content

    def test_get_not_allowed(self, request_factory):
        response = simulate_dissect(request_factory.get('/Utilities/DissectDebugger/simulate/'))
        assert "Invalid request method" in response.content.decode()

    def test_page_renders(self, authenticated_client):
        response = authenticated_client.get('/Utilities/DissectDebugger/')
        assert response.status_code == 200
        assert b"Dissect Debugger" in response.content
