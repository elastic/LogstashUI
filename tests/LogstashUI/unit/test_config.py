#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from LogstashUI.config import load_config, merge_allowed_hosts


def test_merge_allowed_hosts_wildcard_unchanged():
    assert merge_allowed_hosts(allowed="*", host_ips="10.11.3.107") == ["*"]


def test_merge_allowed_hosts_appends_pod_ip():
    hosts = merge_allowed_hosts(
        allowed="logstashui.example.com,logstashui",
        host_ips="10.11.3.107",
        pod_ip="",
    )
    assert hosts == ["logstashui.example.com", "logstashui", "10.11.3.107"]


def test_merge_allowed_hosts_pod_ip_env_and_no_dupes(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "logstashui")
    monkeypatch.setenv("LOGSTASHUI_HOST_IPS", "10.11.3.107")
    monkeypatch.setenv("POD_IP", "10.11.3.107")
    assert merge_allowed_hosts() == ["logstashui", "10.11.3.107"]


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("LOGSTASHUI_NO_AUTH", raising=False)
    monkeypatch.delenv("LOGSTASHUI_AGENT_UI_URL", raising=False)
    monkeypatch.delenv("LOGSTASHUI_INCLUDE_CA_FINGERPRINT", raising=False)
    cfg = load_config()
    assert cfg["no_auth"]["enabled"] is False
    assert cfg["agent"]["ui_url"] == ""
    assert cfg["agent"]["include_ca_fingerprint"] is True


def test_load_config_no_auth_env(monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_NO_AUTH", "true")
    cfg = load_config()
    assert cfg["no_auth"]["enabled"] is True
    monkeypatch.setenv("LOGSTASHUI_NO_AUTH", "0")
    cfg = load_config()
    assert cfg["no_auth"]["enabled"] is False


def test_load_config_agent_env(monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_AGENT_UI_URL", "https://ui.example:8443/")
    monkeypatch.setenv("LOGSTASHUI_INCLUDE_CA_FINGERPRINT", "false")
    cfg = load_config()
    assert cfg["agent"]["ui_url"] == "https://ui.example:8443"
    assert cfg["agent"]["include_ca_fingerprint"] is False


def test_load_config_ignores_yaml_env(monkeypatch, tmp_path):
    yml = tmp_path / "logstashui.yml"
    yml.write_text("no_auth:\n  enabled: true\n")
    monkeypatch.setenv("LOGSTASHUI_CONFIG", str(yml))
    monkeypatch.delenv("LOGSTASHUI_NO_AUTH", raising=False)
    cfg = load_config()
    assert cfg["no_auth"]["enabled"] is False
