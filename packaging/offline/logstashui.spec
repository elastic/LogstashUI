#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# PyInstaller onedir spec for LogstashUI. Experimental: gunicorn+gevent+Django
# hidden imports. Do not change product --worker-class gevent from here.
# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all

SPECDIR = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.abspath(os.path.join(SPECDIR, "..", ".."))
SRC = os.path.join(ROOT, "src", "logstashui")
ENTRY = os.path.join(SPECDIR, "entry.py")

PACKAGES = [
    "LogstashUI",
    "PipelineManager",
    "Management",
    "Utilities",
    "SNMP",
    "Monitoring",
    "Site",
    "Documentation",
    "AI",
    "theme",
    "Common",
    "django",
    "gunicorn",
    "gevent",
    "greenlet",
    "cryptography",
    "pysnmp",
    "lark",
    "pygrok",
    "whitenoise",
    "psycopg",
    "pymysql",
    "yaml",
    "django_htmx",
    "tailwind",
    "login_required",
    "elasticsearch",
    "requests",
    "markdown",
    "packaging",
    "django_browser_reload",
]

datas: list = []
binaries: list = []
hiddenimports: list = []
for pkg in PACKAGES:
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [ENTRY],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="logstashui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="logstashui",
)
