import time
from pathlib import Path

import pytest

from Utilities import grok as grok_module
from Utilities import views
from Utilities.dissect import too_long_int
from Utilities.grok import (
    MAX_EXPANDED_LENGTH,
    PATTERN_SETS,
    Grok,
    GrokError,
    load_patterns,
    looks_like_dissect,
    parse_patterns,
    ruby_to_f,
    ruby_to_i,
)
from Utilities.views import simulate_grok

# Expected values come from running each pattern through Logstash 9.5.5
# (logstash-filter-grok 4.4.4, jls-grok 0.11.5, patterns-core 4.3.4, ecs_compatibility v8).
# None means Logstash tagged the event _grokparsefailure.
VERIFIED_AGAINST_LOGSTASH = [
    ('%{IP:[client][ip]}', '1.2.3.4', {'client': {'ip': '1.2.3.4'}}),
    ('%{IP:client.ip}', '1.2.3.4', {'client.ip': '1.2.3.4'}),
    ('%{WORD:user-agent}', 'curl', {'user-agent': 'curl'}),
    ('%{WORD:[w]}', 'curl', {'w': 'curl'}),
    ('%{WORD:[a][b][c]} %{WORD:[a][d]}', 'x y', {'a': {'b': {'c': 'x'}, 'd': 'y'}}),
    ('(?<queue_id>[0-9A-F]{10,11})', 'id BEF25A72965 x', {'queue_id': 'BEF25A72965'}),
    ('(?<[a][b]>\\d+)', 'n 42', {'a': {'b': '42'}}),
    ('(?<n:int>\\d+)', 'n 42', {'int': '42'}),
    ('%{NUMBER:n:int}', '3.9', {'n': 3}),
    ('%{NOTSPACE:n:int}', '-7apples', {'n': -7}),
    ('%{NOTSPACE:n:int}', '1_000', {'n': 1000}),
    ('%{NOTSPACE:n:int}', 'abc', {'n': 0}),
    ('%{NOTSPACE:n:int}', '0x1A', {'n': 0}),
    ('%{NOTSPACE:n:int}', '+5', {'n': 5}),
    ('x=%{DATA:n:int};', 'x= 12;', {'n': 12}),
    ('%{NOTSPACE:n:float}', '1e3', {'n': 1000.0}),
    ('%{NOTSPACE:n:float}', '.5', {'n': 0.5}),
    ('%{NOTSPACE:n:float}', '1.', {'n': 1.0}),
    ('%{NOTSPACE:n:float}', '12abc', {'n': 12.0}),
    ('%{NOTSPACE:n:float}', 'Infinity', {'n': 0.0}),
    ('%{NOTSPACE:n:float}', '1_000.5', {'n': 1000.5}),
    ('%{NOTSPACE:n:float}', '-.25', {'n': -0.25}),
    ('%{NUMBER:n:long}', '5', {'n': '5'}),
    ('%{NUMBER:n:int:x}', '5', {'n': 5}),
    ('%{NUMBER:n:INT}', '5', {'n': '5'}),
    ('x=%{DATA:n:int};', 'x=;', {'n': 0}),
    ('a=%{DATA:a};', 'a=;', {}),
    ('%{WORD:w}(?: %{INT:n})?', 'word', {'w': 'word'}),
    ('%{WORD} %{INT:n}', 'x 5', {'n': '5'}),
    ('%{WORD:a} %{WORD:a}', 'x y', {'a': ['x', 'y']}),
    ('%{WORD:a} %{NUMBER:a}', 'x 1', {'a': ['x', '1']}),
    ('%{WORD:a} %{NUMBER:a} %{WORD:a}', 'x 1 y', {'a': ['x', 'y', '1']}),
    ('%{NUMBER:a:int} %{WORD:a}', '1 x', {'a': 1}),
    ('%{WORD:a} %{NUMBER:a:int}', 'x 1', {'a': ['x', 1]}),
    ('%{WORD:a} %{WORD:a} %{WORD:a}', 'x y z', {'a': ['x', 'y', 'z']}),
    ('%{WORD:[a][b]} %{WORD:[a][b]}', 'x y', {'a': {'b': ['x', 'y']}}),
    ('%{WORD:a} %{DATA:a};', 'x ;', {'a': 'x'}),
    ('%{NUMBER:a:int} %{NUMBER:a:int}', '1 2', {'a': 1}),
    ('(?:x%{INT:n:int}|y%{INT:n:int})', 'y5', {'n': '5'}),
    ('%{NUMBER:a:float} %{NUMBER:b:int} %{NUMBER:a:float}', '1 2 3', {'a': 1.0, 'b': 2}),
    ('%{WORD:w} %{GREEDYDATA:message}', 'hello world', {'w': 'hello', 'message': ['hello world', 'world']}),
    ('%{WORD:[message]}', 'hello', {'message': ['hello', 'hello']}),
    ('%{WORD:w} %{GREEDYDATA:rest}', 'one two\nthree', {'rest': 'two\nthree', 'w': 'one'}),
    ('^%{WORD:w}$', 'a b\nc', {'w': 'c'}),
    ('a(?<x>.)b', 'a\nb', {'x': '\n'}),
    ('(?m)a(?<x>.)b', 'a\nb', {'x': '\n'}),
    ('(?-m)a(?<x>.)b', 'a\nb', None),
    ('(?<x>x)\\Z', 'ax\n', {'x': 'x'}),
    ('(?<x>x)\\z', 'ax\n', None),
    ('\\A(?<x>b)', 'a\nb', None),
    ('%{WORD:w}', 'José Smith', {'w': 'Smith'}),
    ('(?<w>\\w+)', 'José', {'w': 'Jos'}),
    ('%{USERNAME:u}', 'josé', {'u': 'jos'}),
    ('a(?<s>\\s)b', 'a\xa0b', None),
    ('(?<d>\\d+)', 'x ٣٤ 5', {'d': '5'}),
    ('(?<w>\\b[a-z]+\\b)', 'éa b', {'w': 'b'}),
    ('(?<w>[[:alpha:]]+)', 'José', {'w': 'José'}),
    ('(?<w>\\p{L}+)', 'José', {'w': 'José'}),
    ('(?<h>\\h+)', 'zz 0fA9 x', {'h': '0fA9'}),
    ('(?<h>\\H+)', '0fzz9', {'h': 'zz'}),
    ('(?<h>[\\h-]+)', 'zz 0f-A9 x', {'h': '0f-A9'}),
    ('(?<w>[a-z&&[^aeiou]]+)', 'bad', {'w': 'b'}),
    ('a(?<x>.?*)b', 'a123b', {'x': '123'}),
    ('(?<x>a++)b', 'aaab', {'x': 'aaa'}),
    ('(?<x>(?>a+))b', 'aaab', {'x': 'aaa'}),
    ('<(?<x>.+?)>', '<a><b>', {'x': 'a'}),
    ('(?i)(?<x>abc)', 'xABC', {'x': 'ABC'}),
    ('(?<x>(?i:a)b)', 'AB Ab', {'x': 'Ab'}),
    ('(?<x>[]a]+)', 'x]a]', {'x': ']a]'}),
    ('100\\% %{WORD:w}', '100% done', {'w': 'done'}),
    ('%{WORD:a b}', 'x', {'a': 'x'}),
    ('%{WORD:}', 'x', {}),
    ('%{IP-x:ip}', '1.2.3.4', {}),
    ('%{MYNUM:num=\\d+}', 'n 123', {'num': '123'}),
    ('%{THREE:t=\\d{3}}', 'n 12345', {'t': '123'}),
    ('%{X:a=\\d+}-%{X:b}', '1-2', None),
    ('%{ foo} (?<x>x)', '%{ foo} x', {'x': 'x'}),
    ('%{INT:n}', 'abc 123 def', {'n': '123'}),
    ('%{SYSLOGLINE}', 'Oct  7 11:02:14 web01 sshd[2231]: Accepted publickey for deploy', {
        'host': {'hostname': 'web01'}, 'process': {'pid': 2231, 'name': 'sshd'}, 'timestamp': 'Oct  7 11:02:14',
        'message': ['Oct  7 11:02:14 web01 sshd[2231]: Accepted publickey for deploy', 'Accepted publickey for deploy'],
    }),
    ('%{COMBINEDAPACHELOG}', '1.2.3.4 - frank [10/Oct/2026:13:55:36 -0400] "GET /a?b=1 HTTP/1.1" 200 2326 "-" "curl/8"', {
        'user': {'name': 'frank'},
        'http': {'response': {'body': {'bytes': 2326}, 'status_code': 200}, 'request': {'method': 'GET'}, 'version': '1.1'},
        'source': {'address': '1.2.3.4'}, 'user_agent': {'original': 'curl/8'}, 'url': {'original': '/a?b=1'},
        'timestamp': '10/Oct/2026:13:55:36 -0400',
    }),
    ('%{TIMESTAMP_ISO8601:ts} %{LOGLEVEL:level}', '2026-10-07T11:10:01.123Z WARN', {'ts': '2026-10-07T11:10:01.123Z', 'level': 'WARN'}),
    ('%{IP:ip}', '2001:db8::ff00:42:8329', {'ip': '2001:db8::ff00:42:8329'}),
    ('%{URI:u}', 'https://user:pw@example.com:8443/p/a?q=1#f', {'u': 'https://user:pw@example.com:8443/p/a?q=1#f'}),
    ('%{QS:q}', 'say "hi \\"there\\""', {'q': '"hi \\"there\\""'}),
    ('%{HTTPDATE:d}', '10/Oct/2026:13:55:36 -0400', {'d': '10/Oct/2026:13:55:36 -0400'}),
    ('%{IPORHOST:h}:%{POSINT:p:int}', 'db01.example.com:5432', {'p': 5432, 'h': 'db01.example.com'}),
]


@pytest.mark.parametrize("pattern,message,expected", VERIFIED_AGAINST_LOGSTASH)
def test_verified_against_logstash(pattern, message, expected):
    assert Grok(pattern, load_patterns('v8')).match(message) == expected


def test_legacy_patterns_verified_against_logstash():
    line = '1.2.3.4 - frank [10/Oct/2026:13:55:36 -0400] "GET /a?b=1 HTTP/1.1" 200 2326 "-" "curl/8"'
    assert Grok('%{COMBINEDAPACHELOG}', load_patterns('disabled')).match(line) == {
        'clientip': '1.2.3.4', 'ident': '-', 'auth': 'frank', 'timestamp': '10/Oct/2026:13:55:36 -0400',
        'verb': 'GET', 'request': '/a?b=1', 'httpversion': '1.1', 'response': '200', 'bytes': '2326',
        'referrer': '"-"', 'agent': '"curl/8"',
    }


@pytest.mark.parametrize("ecs", sorted(PATTERN_SETS))
def test_every_bundled_pattern_compiles(ecs):
    patterns = load_patterns(ecs)
    assert len(patterns) > 300
    for name in patterns:
        Grok('%{' + name + '}', patterns)


@pytest.mark.parametrize("pattern,custom,message", [
    ('%{NOPE:x}', {}, r"pattern %\{NOPE:x\} not defined"),
    ('%{IPV:ip}', {}, r"not defined \(did you mean IPV6, IPV4, IP\?\)"),
    ('%{word:w}', {}, r"pattern %\{word:w\} not defined"),
    ('%{LOOP:x}', {'LOOP': '%{LOOP}'}, r"Deep recursion"),
    ('%{A1:x}', {'A1': '%{B1}', 'B1': '%{A1}'}, r"Deep recursion"),
    ('%{WORD:a}(', {}, r"invalid regular expression"),
])
def test_compile_errors(pattern, custom, message):
    with pytest.raises(GrokError, match=message):
        Grok(pattern, {**load_patterns('v8'), **custom})


def test_catastrophic_pattern_times_out():
    grok = Grok('(?<x>(a|a)+)$', {})
    with pytest.raises(TimeoutError):
        grok.match('a' * 40 + 'b', timeout=0.05)


@pytest.mark.parametrize("pattern,message,reason", [
    ('%{IP:ip} %{WORD:verb} %{INT:status}', '1.2.3.4 GET ok',
     "Matched up to '%{IP:ip} %{WORD:verb} ', then '%{INT:status}' did not match 'ok'"),
    ('%{IP:ip} \\[%{HTTPDATE:ts}\\]', '1.2.3.4 (yesterday)',
     "Matched up to '%{IP:ip}', then ' \\[' did not match ' (yesterday)'"),
    ('%{IP:ip} %{WORD:verb}', 'no address here', "'%{IP:ip}' was not found anywhere in the input"),
    ('%{INT:a} %{INT:b}', '1', "Matched up to '%{INT:a}', then ' ' did not match the end of the input"),
])
def test_explain_failure(pattern, message, reason):
    grok = Grok(pattern, load_patterns('v8'))
    assert grok.match(message) is None
    assert grok.explain_failure(message) == reason


@pytest.mark.parametrize("pattern", ['%{IP:ip}|%{WORD:w}', '%{COMBINEDAPACHELOG}', '\\d+ \\w+'])
def test_explain_failure_without_parts(pattern):
    assert Grok(pattern, load_patterns('v8')).explain_failure('!!!') is None


def test_parse_patterns_follows_pattern_files():
    text = "# comment\n  POSTFIX_QUEUEID [0-9A-F]{10,11}\nTRAILING x \nEMPTY\n\nLAST \\d+"
    assert parse_patterns(text) == {
        'POSTFIX_QUEUEID': '[0-9A-F]{10,11}', 'TRAILING': 'x ', 'EMPTY': '', 'LAST': '\\d+',
    }


@pytest.mark.parametrize("value,expected", [("12", 12), (" 7x", 7), ("-0", 0), ("", 0), ("9" * 30, int("9" * 30))])
def test_ruby_to_i(value, expected):
    assert ruby_to_i(value) == expected


def test_ruby_to_i_huge_value_is_a_placeholder():
    assert ruby_to_i("9" * 4300) == int("9" * 4300)
    assert ruby_to_i("-000" + "9" * 5000 + "x") == too_long_int(5000)


def _doubling_patterns(levels):
    patterns = {'P0': '[a-z]' * 200}
    for level in range(1, levels + 1):
        patterns[f'P{level}'] = f'%{{P{level - 1}}}%{{P{level - 1}}}'
    return patterns


def test_runaway_expansion_is_rejected_quickly():
    start = time.monotonic()
    with pytest.raises(GrokError, match=f'more than {MAX_EXPANDED_LENGTH} characters'):
        Grok('%{P20}', _doubling_patterns(20))
    assert time.monotonic() - start < 2


def test_compile_respects_deadline():
    with pytest.raises(TimeoutError):
        Grok('%{P10}', _doubling_patterns(10), deadline=time.monotonic() - 1)


def test_explain_failure_on_long_pattern_is_fast():
    grok = Grok('%{WORD} ' * 800 + '%{INT:x}', load_patterns())
    start = time.monotonic()
    reason = grok.explain_failure('a ' * 800 + 'zz')
    assert time.monotonic() - start < 2
    assert reason.endswith("then '%{INT:x}' did not match 'zz'")


def test_explain_failure_skips_prefixes_that_do_not_compile(monkeypatch):
    patterns = load_patterns()
    grok = Grok('%{WORD:a} %{WORD:b} %{INT:c}', patterns)
    real_compile = grok_module._compile

    def compile_except_first_cut(pattern, patterns, deadline=None):
        if pattern == '%{WORD:a}':
            raise GrokError('cannot compile')
        return real_compile(pattern, patterns, deadline)

    monkeypatch.setattr(grok_module, '_compile', compile_except_first_cut)
    assert grok.explain_failure('x y z') == "Matched up to '%{WORD:a} %{WORD:b} ', then '%{INT:c}' did not match 'z'"


@pytest.mark.parametrize('template', ['grok_debugger.html', 'dissect_debugger.html'])
def test_templates_show_spinner_and_drop_repeat_submits(template):
    import Utilities
    content = (Path(Utilities.__file__).parent / 'templates' / template).read_text()
    assert 'htmx-indicator hidden' not in content
    assert 'hx-sync="this:drop"' in content


@pytest.mark.parametrize("value,expected", [("1.5e2", 150.0), ("-", 0.0), ("1e", 1.0), ("+.5", 0.5)])
def test_ruby_to_f(value, expected):
    assert ruby_to_f(value) == expected


@pytest.mark.parametrize("pattern,expected", [
    ("%{a} %{b}", True), ("%{} %{?x}", True), ("%{+ts} %{&k}", True), ("%{ts->}", True),
    ("%{WORD:a}", False), ("%{IP}", False), ("(?<a>x)", False),
])
def test_looks_like_dissect(pattern, expected):
    assert looks_like_dissect(pattern) is expected


@pytest.mark.django_db
class TestSimulateGrokView:
    def _post(self, request_factory, **data):
        data.setdefault('custom_patterns', '')
        return simulate_grok(request_factory.post('/Utilities/GrokDebugger/simulate/', data)).content.decode()

    def test_ecs_compatibility_selects_pattern_set(self, request_factory):
        line = '1.2.3.4 - - [10/Oct/2026:13:55:36 -0400] "GET / HTTP/1.1" 200 5 "-" "curl"'
        ecs = self._post(request_factory, sample_data=line, grok_pattern='%{COMBINEDAPACHELOG}')
        legacy = self._post(request_factory, sample_data=line, grok_pattern='%{COMBINEDAPACHELOG}', ecs_compatibility='disabled')
        assert '&quot;address&quot;: &quot;1.2.3.4&quot;' in ecs and 'clientip' not in ecs
        assert '&quot;clientip&quot;: &quot;1.2.3.4&quot;' in legacy

    def test_unknown_ecs_value_falls_back_to_v8(self, request_factory):
        content = self._post(request_factory, sample_data='1.2.3.4 - - [10/Oct/2026:13:55:36 -0400] "GET / HTTP/1.1" 200 5',
                             grok_pattern='%{COMMONAPACHELOG}', ecs_compatibility='v99')
        assert '&quot;address&quot;' in content

    def test_custom_patterns_override_builtins(self, request_factory):
        content = self._post(request_factory, sample_data='ABC def', grok_pattern='%{WORD:w}', custom_patterns='WORD [a-z]+')
        assert '&quot;w&quot;: &quot;def&quot;' in content

    def test_failure_explains_where_matching_stopped(self, request_factory):
        content = self._post(request_factory, sample_data='1.2.3.4 GET ok', grok_pattern='%{IP:ip} %{WORD:verb} %{INT:status}')
        assert '_grokparsefailure: Matched up to' in content
        assert '%{INT:status}' in content

    def test_compile_error_and_dissect_warning(self, request_factory):
        content = self._post(request_factory, sample_data='x y', grok_pattern='%{a} %{b}')
        assert 'Pattern compilation error: pattern %{a} not defined' in content
        assert 'This looks like a dissect pattern' in content

    def test_character_class_warning(self, request_factory):
        content = self._post(request_factory, sample_data='1.2.3.4 [x]', grok_pattern='%{IP:ip} [%{DATA:d}]')
        assert 'An unescaped [ starts a regex character class' in content

    def test_message_capture_warning(self, request_factory):
        content = self._post(request_factory, sample_data='Oct  7 11:02:14 web01 sshd[1]: hi', grok_pattern='%{SYSLOGLINE}')
        assert 'overwrite =&gt; [&quot;message&quot;]' in content

    def test_timeout_is_reported(self, request_factory, monkeypatch):
        monkeypatch.setattr(views, 'GROK_MATCH_TIMEOUT', 0.05)
        content = self._post(request_factory, sample_data='a' * 40 + 'b', grok_pattern='(?<x>(a|a)+)$')
        assert '_groktimeout' in content

    def test_request_time_limit_skips_remaining_lines(self, request_factory, monkeypatch):
        monkeypatch.setattr(views, 'REQUEST_TIMEOUT', 0)
        content = self._post(request_factory, sample_data='a\nb', grok_pattern='%{WORD:w}\n%{INT:n}')
        assert content.count('Skipped: this simulation hit the 0 second limit.') == 4

    def test_huge_int_returns_placeholder(self, request_factory):
        content = self._post(request_factory, sample_data='9' * 5000, grok_pattern='%{NOTSPACE:n:int}')
        assert 'integer with 5000 digits, too large to display' in content

    def test_runaway_custom_pattern_is_a_compile_error(self, request_factory):
        custom = '\n'.join(f'{name} {value}' for name, value in _doubling_patterns(20).items())
        start = time.monotonic()
        content = self._post(request_factory, sample_data='a', grok_pattern='%{P20}', custom_patterns=custom)
        assert 'too large for the debugger to compile' in content
        assert time.monotonic() - start < 2

    def test_crlf_is_normalized(self, request_factory):
        content = self._post(request_factory, sample_data='a 1\r\nb 2', grok_pattern='%{WORD:w} %{INT:n}$\r\n')
        assert content.count('Match Found') == 2

    def test_page_uses_codemirror(self, authenticated_client):
        content = authenticated_client.get('/Utilities/GrokDebugger/').content.decode()
        assert 'codemirror.min.js' in content and 'grok_debugger.js' in content
        assert 'name="ecs_compatibility"' in content
