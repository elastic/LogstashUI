# Air-gapped freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optional `bin/freeze_logstashui.sh` emits Linux x86_64 wheelhouse, Docker, and experimental PyInstaller zips so an air-gapped host can run LogstashUI with no PyPI or registry.

**Architecture:** Connected builder runs a bash script (not a CLI subcommand). Default `uv build` is unchanged. Isolated helpers (`install.sh` / `load.sh` / `run.sh`) live in each zip. Templates and the PyInstaller spec live in `packaging/offline/`. `os.execvp("gunicorn")` cannot work inside PyInstaller; `cli.py` gets a frozen in-process gunicorn path without changing `--worker-class gevent`.

**Tech Stack:** bash, uv, pip download (manylinux2014_x86_64 / cp312), Docker save, PyInstaller onedir, MkDocs-style docs.

**Spec:** `docs/superpowers/specs/2026-09-02-airgap-freeze-design.md`

---

## File map

| Path | Role |
|---|---|
| `bin/freeze_logstashui.sh` | Builder |
| `bin/test_freeze_wheels.sh` | Unzip + `docker run --platform linux/amd64 --network=none` install smoke |
| `packaging/offline/*` | Templates + PyInstaller spec/entry |
| `src/logstashui/LogstashUI/cli.py` | Frozen gunicorn exec |
| `docs/docs/logstashui/general/offline.md` | Operator + maintainer docs |
| `docs/docs/logstashui/general/deploy.md` | Option 6 |
| `CHANGELOG.md` | 0.5.2 packaging note |
| `.github/workflows/offline-freeze.yml` | `workflow_dispatch` `--wheels` only |

### Task 1: Templates + freeze script + docs + frozen hook

Implement per spec. `--all` on non-Linux-x86_64 skips standalone with a warning; explicit `--standalone` fails. Never `docker pull`. `pip download` without `--abi` (so `py3-none-any` wheels are kept). Builder requires `uv python find 3.12`.

### Task 2: Wheels smoke

`bin/freeze_logstashui.sh --wheels` then `bin/test_freeze_wheels.sh`.
