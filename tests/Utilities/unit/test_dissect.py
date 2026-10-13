import time

import pytest

from Utilities import views
from Utilities.dissect import Dissector, DissectError, DissectFailure, looks_like_grok, too_long_int
from Utilities.views import parse_convert_datatype, simulate_dissect, simulate_grok, split_sample_lines


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

    @pytest.mark.parametrize("pattern,text,expected", [
        ("%{+a/2} %{+a/1} %{+a/4} %{+a/3}", "1 2 3 go", {"a": "2 1 go 3"}),
        ("%{a} %{b} %{+a}", "1 2 3 go", {"a": "1 3 go", "b": "2"}),
        ("%{a}-%{+a}:%{+a}", "1-2:3", {"a": "1-2:3"}),
        ("%{+a} %{a}", "1 2", {"a": "2 1"}),
    ])
    def test_append(self, pattern, text, expected):
        """Pieces are joined with the delimiter before each piece (or a space), normal fields first."""
        assert Dissector(pattern).match(text) == expected

    def test_right_padding(self):
        assert Dissector("%{ts->} %{level} %{msg}").match("12:00    INFO started up") == {
            "ts": "12:00",
            "level": "INFO",
            "msg": "started up",
        }

    @pytest.mark.parametrize("pattern,text,expected", [
        ("%{a} %{b} %{c}", "x  y", {"a": "x", "b": "", "c": "y"}),
        ("%{a} %{b}", "x ", {"a": "x", "b": ""}),
        ("T4 %{a} %{b}", "T4  y", {"a": "", "b": "y"}),
        ("%{a} %{+a} %{+a}", "x  z", {"a": "x  z"}),
        # Without a prefix, a delimiter at position 0 doesn't advance, so the next field re-reads it.
        ("%{a} %{b}", " y", {"a": "", "b": " y"}),
    ])
    def test_empty_values_are_kept(self, pattern, text, expected):
        """Empty captures are set as "" and still joined when appended."""
        assert Dissector(pattern).match(text) == expected

    def test_skip_fields(self):
        assert Dissector("%{a} %{} %{?ignored} %{b}").match("1 2 3 4") == {"a": "1", "b": "4"}

    @pytest.mark.parametrize("pattern,text,expected", [
        ("%{?k}: %{&k}", "foo: bar", {"foo": "bar"}),
        ("%{&k}: %{?k}", "bar: foo", {"foo": "bar"}),
        ("%{k}: %{&k}", "foo: bar", {"k": "foo", "foo": "bar"}),
        ("error: %{?err}, %{&err}", "error: some_error, description", {"some_error": "description"}),
        ("%{?k}=%{&k}", "=value", {}),
        ("%{*k}=%{&k}", "foo=bar", {"*k": "foo"}),
    ])
    def test_indirect_fields(self, pattern, text, expected):
        """``*`` is not a prefix in Logstash, so ``%{*k}`` is a normal field named ``*k``."""
        assert Dissector(pattern).match(text) == expected

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
        assert dissector.match("512 1.5 nope") == {
            "bytes": 512, "ms": 1.5, "bad": "nope", "tags": ["_dataconversionuncoercible_bad_int"]
        }

    @pytest.mark.parametrize("pattern,text,convert,expected", [
        ("T1 %{client.ip} %{[client][port]} %{[server][name]}", "T1 1.2.3.4 80 web01", None,
         {"client.ip": "1.2.3.4", "client": {"port": "80"}, "server": {"name": "web01"}}),
        ("T7 %{a} - %{b}.", "T7 x - y. extra", None, {"a": "x", "b": "y"}),
        ("T9 %{a} %{b} %{c}", "T9 3.5 - abc", {"a": "int", "b": "int", "c": "float"},
         {"a": 3, "b": "-", "c": "abc",
          "tags": ["_dataconversionuncoercible_b_int", "_dataconversionuncoercible_c_float"]}),
        ("T10 %{*k}=%{&k}", "T10 =value", None, {"*k": ""}),
        ("T13 %{a} %{a}", "T13 x y", None, {"a": "y"}),
        ("T14 %{+a/2} %{+a} %{+a/1}", "T14 x y z", None, {"a": "y zT14 x"}),
        ("T15 %{a} %{->} %{b}", "T15 x    y", None, {"a": "x", "": "", "b": "y"}),
        ("T16 %{a} %{b->}", "T16 x y   ", None, {"a": "x", "b": "y   "}),
        ("T18 %{&k}=%{*k}", "T18 value=key", None, {"*k": "key"}),
        ("T19 %{a->}, %{b}", "T19 x, , , y", None, {"a": "x", "b": "y"}),
        ("%{tags} %{a}", "hello world", {"missing": "int"},
         {"tags": ["hello", "_dataconversionnullvalue_missing_int"], "a": "world"}),
    ])
    def test_verified_against_logstash(self, pattern, text, convert, expected):
        """Outputs captured from a real Logstash run."""
        assert Dissector(pattern, convert_datatype=convert).match(text) == expected

    @pytest.mark.parametrize("pattern,text", [
        ("[%{level}] %{msg}", "T8 [WARN] disk low"),
        ("T11 %{a} %{b}.", "T11 x y"),
        ("T20 %{a} %{b}", "T20 x"),
    ])
    def test_verified_failures_against_logstash(self, pattern, text):
        with pytest.raises(DissectFailure):
            Dissector(pattern).match(text)

    def test_failure_message_shows_delimiter_as_typed(self):
        with pytest.raises(DissectFailure) as excinfo:
            Dissector(r"%{a}\[%{b}").match("x y")
        assert r"'\['" in str(excinfo.value)
        assert r"\\" not in str(excinfo.value)

    def test_adjacent_fields_never_match(self):
        with pytest.raises(DissectFailure, match="never matches"):
            Dissector("%{a}%{b}").match("xy")

    def test_missing_conversion_field_is_tagged(self):
        assert Dissector("%{a}", convert_datatype={"b": "int"}).match("1") == {
            "a": "1", "tags": ["_dataconversionnullvalue_b_int"]
        }

    @pytest.mark.parametrize("value,datatype,expected", [
        ("-7.9", "int", -7), ("1e3", "int", 1000), (".5", "float", 0.5), ("+2", "INT", 2),
    ])
    def test_conversion_accepts_big_decimal_formats(self, value, datatype, expected):
        assert Dissector("%{a}", convert_datatype={"a": datatype}).match(value)["a"] == expected

    @pytest.mark.parametrize("value,digits", [("1e4300", 4301), ("1e999999", 1000000), (".5e5000", 5000), ("9" * 5000, 5000)])
    def test_huge_int_conversion_is_a_placeholder(self, value, digits):
        start = time.monotonic()
        result = Dissector("%{a}", convert_datatype={"a": "int"}).match(value)
        assert result == {"a": too_long_int(digits)}
        assert time.monotonic() - start < 1

    def test_largest_displayable_int_is_converted(self):
        assert Dissector("%{a}", convert_datatype={"a": "int"}).match("1e4299")["a"] == 10 ** 4299

    @pytest.mark.parametrize("value", ["nan", "inf", "1_000", " 3", "0x10"])
    def test_conversion_rejects_what_big_decimal_rejects(self, value):
        assert Dissector("x%{a}", convert_datatype={"a": "float"}).match("x" + value)["tags"] == [
            "_dataconversionuncoercible_a_float"
        ]

    @pytest.mark.parametrize("pattern", ["no fields", "%{+}", "%{&}", "%{+->}", "%{+&a}", "%{&+a}"])
    def test_invalid_patterns(self, pattern):
        with pytest.raises(DissectError):
            Dissector(pattern)

    def test_invalid_datatype(self):
        with pytest.raises(DissectError):
            Dissector("%{a}", convert_datatype={"a": "bool"})


@pytest.mark.parametrize("pattern", [r"%{IP:ip}", r"%{DATA:program}\[", r"%{a}\s%{b}"])
def test_looks_like_grok(pattern):
    assert looks_like_grok(pattern)


@pytest.mark.parametrize("pattern", [
    "%{IP}",
    "%{a} [%{b}]",
    '%{clientip} %{} %{auth} [%{timestamp}] "%{verb} %{request} HTTP/%{httpversion}" %{response} %{bytes} "%{referrer}" "%{agent}"',
    "%{timestamp->} %{+timestamp} %{+timestamp} %{host} %{program}[%{pid}]: %{msg}",
    "%{timestamp} %{*f1}=%{&f1} %{*f2}=%{&f2}",
    "%{timestamp} %{+timestamp} %{level->} %{}[%{thread}] %{logger} - %{msg}",
    "%{txn_id}|%{user}|%{type}|%{amount}|%{qty}",
])
def test_does_not_look_like_grok(pattern):
    assert not looks_like_grok(pattern)


def test_split_sample_lines():
    assert split_sample_lines("a\n\nb\n  \nc", False) == [(1, "a"), (3, "b"), (5, "c")]
    assert split_sample_lines("a\n\nb", True) == [(1, "a\n\nb")]
    assert split_sample_lines("  \n", True) == []


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
        content = self._post(request_factory, sample_data="x", dissect_pattern="%{+}").content.decode()
        assert "Pattern compilation error" in content

    def test_grok_pattern_warning(self, request_factory):
        grok = r"%{SYSLOGTIMESTAMP:timestamp} %{SYSLOGHOST:host} %{DATA:program}\[%{POSINT:pid}\]: %{GREEDYDATA:msg}"
        content = self._post(request_factory, sample_data="x", dissect_pattern=grok).content.decode()
        assert "looks like a grok pattern" in content
        content = self._post(request_factory, sample_data="x y", dissect_pattern="%{a} %{b}").content.decode()
        assert "looks like a grok pattern" not in content

    def test_sample_whitespace_is_preserved_in_cards(self, request_factory):
        content = self._post(request_factory, sample_data="Oct  7 x", dissect_pattern="%{a} %{b}").content.decode()
        assert "whitespace-pre-wrap" in content
        assert ">Oct  7 x</p>" in content

    def test_line_numbers_match_editor(self, request_factory):
        content = self._post(request_factory, sample_data="a 1\n\nb 2\n   \nc 3", dissect_pattern="%{k} %{v}").content.decode()
        assert "Line 1 - " in content and "Line 3 - " in content and "Line 5 - " in content
        assert "Line 2 - " not in content

    @pytest.mark.parametrize("sample,pattern,message", [
        ("", "%{a}", "Enter some sample data"),
        ("   \n", "%{a}", "Enter some sample data"),
        ("x", "", "Enter at least one dissect pattern"),
    ])
    def test_missing_input_message(self, request_factory, sample, pattern, message):
        content = self._post(request_factory, sample_data=sample, dissect_pattern=pattern).content.decode()
        assert message in content
        assert "Pattern 1" not in content

    @pytest.mark.parametrize("convert", ["a => int extra", "a => bool"])
    def test_convert_datatype_error_reported_once(self, request_factory, convert):
        content = self._post(
            request_factory, sample_data="1\n2\n3", dissect_pattern="%{a}", convert_datatype=convert
        ).content.decode()
        assert content.count("Options &gt; convert_datatype") == 1
        assert "Pattern compilation error" not in content and "Pattern 1" not in content

    def test_grok_shares_line_numbers_and_empty_message(self, request_factory):
        def grok(**data):
            data.setdefault('custom_patterns', '')
            return simulate_grok(request_factory.post('/Utilities/GrokDebugger/simulate/', data)).content.decode()

        content = grok(sample_data="1.1.1.1\n\n2.2.2.2", grok_pattern="%{IP:ip}")
        assert "Line 1 - " in content and "Line 3 - " in content and "Line 2 - " not in content
        assert "Enter at least one grok pattern" in grok(sample_data="1.1.1.1", grok_pattern="")
        assert "Enter some sample data" in grok(sample_data="", grok_pattern="%{IP:ip}")

    def test_multiline_mode(self, request_factory):
        content = self._post(
            request_factory, sample_data="a\nb", dissect_pattern="%{msg}", multiline_mode="true"
        ).content.decode()
        assert "1 matched" in content

    def test_multiline_crlf_is_normalized(self, request_factory):
        content = self._post(
            request_factory, sample_data="a b\r\nc d", dissect_pattern="%{x} %{y}\r\n",
            convert_datatype="x => int\r\n", multiline_mode="true",
        ).content.decode()
        assert "1 matched" in content and "&quot;y&quot;: &quot;b\\nc d&quot;" in content
        assert "\\r" not in content and "\r" not in content

    def test_huge_int_returns_placeholder(self, request_factory):
        response = self._post(request_factory, sample_data="1e999999", dissect_pattern="%{a}", convert_datatype="a => int")
        assert response.status_code == 200
        assert "integer with 1000000 digits, too large to display" in response.content.decode()

    def test_request_time_limit_skips_lines(self, request_factory, monkeypatch):
        monkeypatch.setattr(views, 'REQUEST_TIMEOUT', 0)
        content = self._post(request_factory, sample_data="a\nb", dissect_pattern="%{a}").content.decode()
        assert content.count("Skipped: this simulation hit the 0 second limit.") == 2

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
        assert b"codemirror.min.js" in response.content
        assert b"debugger_editor.js" in response.content
