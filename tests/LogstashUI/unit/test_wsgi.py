#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from LogstashUI.wsgi import build_application


def test_build_application_inits_telemetry_before_handler(monkeypatch):
    order = []

    def fake_init():
        order.append("init")

    def fake_get_wsgi():
        order.append("get_wsgi")
        return object()

    monkeypatch.setattr("LogstashUI.telemetry.init_telemetry", fake_init)
    monkeypatch.setattr("django.core.wsgi.get_wsgi_application", fake_get_wsgi)

    result = build_application()
    assert order == ["init", "get_wsgi"]
    assert result is not None
