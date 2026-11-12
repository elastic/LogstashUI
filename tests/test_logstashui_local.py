#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# acceptance #6
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packaging" / "offline" / "logstashui_local.sh"
SYSTEM_PYTHON = "/usr/bin/python3"

SHIM = """#!/usr/bin/python3
import json
import os
import shutil
import sys
import zipfile

def log():
    rec = {"argv": sys.argv, "data_dir": os.environ.get("LOGSTASHUI_DATA_DIR")}
    with open(os.environ["SHIM_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\\n")

args = sys.argv[1:]
if args[:1] == ["-c"]:
    log()
    sys.exit(0)
if args[:2] == ["-m", "venv"]:
    log()
    dest = args[-1]
    bindir = os.path.join(dest, "bin")
    os.makedirs(bindir, exist_ok=True)
    target = os.path.join(bindir, "python")
    shutil.copy2(os.path.abspath(sys.argv[0]), target)
    os.chmod(target, 0o755)
    sys.exit(0)
if args[:2] == ["-m", "pip"]:
    log()
    bindir = os.path.dirname(os.path.abspath(sys.argv[0]))
    dest = os.path.join(bindir, "logstashui")
    shutil.copy2(os.path.abspath(sys.argv[0]), dest)
    os.chmod(dest, 0o755)
    sys.exit(0)
if args[:3] == ["-m", "zipfile", "-e"]:
    zipfile.ZipFile(args[3]).extractall(args[4])
    log()
    sys.exit(0)
log()
sys.exit(0)
"""


def here_of(script: Path) -> str:
    out = subprocess.check_output(
        ["sh", "-c", 'CDPATH= cd -- "$(dirname "$1")" && pwd', "sh", str(script)],
        text=True,
    )
    return out.strip()


def tools_dir(tmp: Path) -> str:
    bindir = tmp / "tools"
    bindir.mkdir()
    for name in ("dirname", "cat", "mktemp", "mkdir", "chmod", "rm", "cp"):
        src = shutil.which(name)
        if not src:
            raise RuntimeError(f"missing tool {name}")
        os.symlink(src, bindir / name)
    return str(bindir)


def write_shim(directory: Path, name: str = "python3.12") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(SHIM)
    path.chmod(0o755)
    return path


def copy_script(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    script = dest_dir / "logstashui_local.sh"
    shutil.copy2(SCRIPT, script)
    script.chmod(0o755)
    return script


def make_wheels(parent: Path) -> Path:
    wheels = parent / "wheels"
    wheels.mkdir(parents=True)
    (wheels / "dummy.whl").write_bytes(b"wheel")
    return wheels


def plant_venv(venv: Path, shim: Path) -> None:
    bindir = venv / "bin"
    bindir.mkdir(parents=True)
    for name in ("python", "logstashui"):
        dest = bindir / name
        shutil.copy2(shim, dest)
        dest.chmod(0o755)


def read_log(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            rows.append(json.loads(line))
    return rows


def pip_rows(rows: list) -> list:
    return [row for row in rows if row["argv"][1:3] == ["-m", "pip"]]


def env_for(tmp: Path, tools: str, *, path_prefix=None, python=None, data_dir=None) -> dict:
    parts = []
    if path_prefix:
        parts.append(path_prefix)
    parts.append(tools)
    env = {
        "PATH": ":".join(parts),
        "HOME": str(tmp),
        "TMPDIR": str(tmp),
        "SHIM_LOG": str(tmp / "shim.log"),
    }
    if python:
        env["PYTHON"] = python
    if data_dir is not None:
        env["LOGSTASHUI_DATA_DIR"] = data_dir
    return env


def run(script: Path, args: list, env: dict, cwd: Path):
    return subprocess.run(
        [str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def other_cwd(tmp: Path) -> Path:
    cwd = tmp / "elsewhere"
    cwd.mkdir(exist_ok=True)
    return cwd


def live_pid(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")


# acceptance #6
def test_help_exits_zero(tmp_path):
    script = copy_script(tmp_path / "bundle")
    env = env_for(tmp_path, tools_dir(tmp_path))
    for flag in ("-h", "--help"):
        proc = run(script, [flag], env, tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.startswith("usage: logstashui_local.sh")


# acceptance #6
def test_help_without_python(tmp_path):
    script = copy_script(tmp_path / "bundle")
    env = env_for(tmp_path, tools_dir(tmp_path))
    assert not any(Path(part, name).exists() for part in env["PATH"].split(":") for name in ("python", "python3", "python3.12"))
    proc = run(script, ["--help"], env, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("usage: logstashui_local.sh")


# acceptance #6
def test_bare_and_unknown_invocation(tmp_path):
    script = copy_script(tmp_path / "bundle")
    env = env_for(tmp_path, tools_dir(tmp_path))
    bare = run(script, [], env, tmp_path)
    bogus = run(script, ["--bogus"], env, tmp_path)
    for proc in (bare, bogus):
        assert proc.returncode == 1
        assert "usage: logstashui_local.sh" in proc.stderr


# acceptance #6
def test_install_missing_python(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    make_wheels(bundle)
    env = env_for(tmp_path, tools_dir(tmp_path))
    env.pop("PYTHON", None)
    proc = run(script, ["--install"], env, other_cwd(tmp_path))
    assert proc.returncode == 1
    assert "need CPython 3.12 x86_64" in proc.stderr
    assert not (bundle / ".venv").exists()


# acceptance #6
def test_python_validation(tmp_path):
    assert sys.version_info[:2] != (3, 12)
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    make_wheels(bundle)
    shim_dir = tmp_path / "shims"
    write_shim(shim_dir, "python3.12")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(shim_dir), python=SYSTEM_PYTHON)
    proc = run(script, ["--install"], env, other_cwd(tmp_path))
    assert proc.returncode == 1
    assert "need CPython 3.12 x86_64" in proc.stderr
    assert not (bundle / ".venv").exists()
    assert pip_rows(read_log(tmp_path / "shim.log")) == []


# acceptance #6
def test_python_precedence(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    make_wheels(bundle)
    chosen = write_shim(tmp_path / "chosen", "python")
    path_py = write_shim(tmp_path / "onpath", "python3.12")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(path_py.parent), python=str(chosen))
    proc = run(script, ["--install"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = read_log(tmp_path / "shim.log")
    venv_rows = [row for row in rows if row["argv"][1:3] == ["-m", "venv"]]
    assert venv_rows
    assert all(row["argv"][0] == str(chosen) for row in venv_rows)
    assert all(row["argv"][0] != str(path_py) for row in rows)
    assert (bundle / ".venv").is_dir()


# acceptance #6
def test_install_missing_wheels(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    shim = write_shim(tmp_path / "shims")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(shim.parent))
    proc = run(script, ["--install"], env, other_cwd(tmp_path))
    assert proc.returncode == 1
    assert "missing wheels directory" in proc.stderr
    assert not (bundle / ".venv").exists()


# acceptance #6
def test_install_custom_path(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    make_wheels(bundle)
    install = tmp_path / "opt"
    shim = write_shim(tmp_path / "shims")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(shim.parent))
    proc = run(script, ["--install-path", str(install), "--install"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert (install / ".venv").is_dir()
    assert not (bundle / ".venv").exists()


# acceptance #6
def test_install_pip_argv(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    make_wheels(bundle)
    here = here_of(script)
    write_shim(tmp_path / "shims")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(tmp_path / "shims"))
    proc = run(script, ["--install"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = pip_rows(read_log(tmp_path / "shim.log"))
    assert rows
    assert rows[0]["argv"] == [
        f"{here}/.venv/bin/python",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-index",
        "--no-cache-dir",
        "--find-links",
        f"{here}/wheels",
        "LogstashUI[databases,otel]",
    ]


# acceptance #6
def test_serve_auto_installs(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    make_wheels(bundle)
    here = here_of(script)
    assert not (bundle / ".venv").exists()
    write_shim(tmp_path / "shims")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(tmp_path / "shims"))
    proc = run(script, ["serve"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = read_log(tmp_path / "shim.log")
    pip = pip_rows(rows)
    serve = [row for row in rows if row["argv"][1:] == ["serve"]]
    assert pip and serve
    assert rows.index(pip[0]) < rows.index(serve[0])
    assert pip[0]["argv"] == [
        f"{here}/.venv/bin/python",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-index",
        "--no-cache-dir",
        "--find-links",
        f"{here}/wheels",
        "LogstashUI[databases,otel]",
    ]
    assert serve[0]["argv"] == [f"{here}/.venv/bin/logstashui", "serve"]


# acceptance #6
def test_serve_alias_and_passthrough(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    here = here_of(script)
    shim = write_shim(tmp_path / "shims")
    plant_venv(bundle / ".venv", shim)
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(shim.parent), python=str(shim))
    proc = run(script, ["--serve", "--host", "127.0.0.1"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = read_log(tmp_path / "shim.log")
    assert [f"{here}/.venv/bin/logstashui", "serve", "--host", "127.0.0.1"] in [
        row["argv"] for row in rows
    ]


# acceptance #6
def test_serve_exports_data_dir(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    here = here_of(script)
    shim = write_shim(tmp_path / "shims")
    plant_venv(bundle / ".venv", shim)
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(shim.parent), python=str(shim))
    assert "LOGSTASHUI_DATA_DIR" not in env
    proc = run(script, ["serve"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = [row for row in read_log(tmp_path / "shim.log") if row["argv"][1:] == ["serve"]]
    assert rows
    assert rows[0]["data_dir"] == f"{here}/logstashui_data"


# acceptance #6
def test_serve_install_path_exports_data_dir(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    install = tmp_path / "opt"
    shim = write_shim(tmp_path / "shims")
    plant_venv(install / ".venv", shim)
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(shim.parent), python=str(shim))
    proc = run(script, ["--install-path", str(install), "serve"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = [row for row in read_log(tmp_path / "shim.log") if row["argv"][1:] == ["serve"]]
    assert rows
    assert rows[0]["data_dir"] == str(install / "logstashui_data")


# acceptance #6
def test_serve_preserves_custom_data_dir_env(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    shim = write_shim(tmp_path / "shims")
    plant_venv(bundle / ".venv", shim)
    custom = str(tmp_path / "custom data")
    env = env_for(
        tmp_path,
        tools_dir(tmp_path),
        path_prefix=str(shim.parent),
        python=str(shim),
        data_dir=custom,
    )
    proc = run(script, ["serve"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = [row for row in read_log(tmp_path / "shim.log") if row["argv"][1:] == ["serve"]]
    assert rows
    assert rows[0]["data_dir"] == custom


# acceptance #6
def test_upgrade_missing_venv(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    env = env_for(tmp_path, tools_dir(tmp_path))
    proc = run(script, ["--upgrade", str(tmp_path / "missing-bundle")], env, other_cwd(tmp_path))
    assert proc.returncode == 1
    assert "error: no existing virtualenv found to upgrade" in proc.stderr
    assert not (bundle / ".venv").exists()


def _guard_bundle(tmp: Path):
    bundle = tmp / "bundle"
    script = copy_script(bundle)
    shim = write_shim(tmp / "shims")
    archive = tmp / "archive"
    make_wheels(archive)
    return script, shim, archive


# acceptance #6
def test_upgrade_running_server_guard(tmp_path):
    script, shim, archive = _guard_bundle(tmp_path)
    here = here_of(script)
    plant_venv(Path(here) / ".venv", shim)
    live_pid(Path(here) / "logstashui_data" / "gunicorn.pid")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(shim.parent), python=str(shim))
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 1
    assert "error: logstashui server is running. Stop server before upgrading." in proc.stderr
    assert pip_rows(read_log(tmp_path / "shim.log")) == []


# acceptance #6
def test_upgrade_running_server_guard_install_path(tmp_path):
    script, shim, archive = _guard_bundle(tmp_path)
    install = tmp_path / "opt"
    plant_venv(install / ".venv", shim)
    live_pid(install / "logstashui_data" / "gunicorn.pid")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=str(shim.parent), python=str(shim))
    proc = run(
        script,
        ["--install-path", str(install), "--upgrade", str(archive)],
        env,
        other_cwd(tmp_path),
    )
    assert proc.returncode == 1
    assert "error: logstashui server is running. Stop server before upgrading." in proc.stderr
    assert pip_rows(read_log(tmp_path / "shim.log")) == []


# acceptance #6
def test_upgrade_running_server_guard_preset_env(tmp_path):
    script, shim, archive = _guard_bundle(tmp_path)
    here = here_of(script)
    plant_venv(Path(here) / ".venv", shim)
    custom = tmp_path / "preset-data"
    live_pid(custom / "gunicorn.pid")
    env = env_for(
        tmp_path,
        tools_dir(tmp_path),
        path_prefix=str(shim.parent),
        python=str(shim),
        data_dir=str(custom),
    )
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 1
    assert "error: logstashui server is running. Stop server before upgrading." in proc.stderr
    assert pip_rows(read_log(tmp_path / "shim.log")) == []


def _upgrade_ready(tmp: Path, install: Path | None = None):
    bundle = tmp / "bundle"
    script = copy_script(bundle)
    shim = write_shim(tmp / "shims")
    root = install if install is not None else Path(here_of(script))
    plant_venv(root / ".venv", shim)
    env = env_for(tmp, tools_dir(tmp), path_prefix=str(shim.parent), python=str(shim))
    return script, env


# acceptance #6
def test_upgrade_pip_and_migrate_argv(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    here = here_of(script)
    archive = tmp_path / "archive"
    make_wheels(archive)
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = read_log(tmp_path / "shim.log")
    pip = pip_rows(rows)
    migrate = [row for row in rows if row["argv"][1:] == ["manage", "migrate", "--noinput"]]
    assert pip and migrate
    assert pip[0]["argv"] == [
        f"{here}/.venv/bin/python",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-index",
        "--no-cache-dir",
        "--find-links",
        str(archive / "wheels"),
        "--upgrade",
        "--upgrade-strategy",
        "eager",
        "LogstashUI[databases,otel]",
    ]
    assert migrate[0]["argv"] == [
        f"{here}/.venv/bin/logstashui",
        "manage",
        "migrate",
        "--noinput",
    ]


# acceptance #6
def test_upgrade_migrate_exports_data_dir(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    here = here_of(script)
    archive = tmp_path / "archive"
    make_wheels(archive)
    assert "LOGSTASHUI_DATA_DIR" not in env
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = [
        row
        for row in read_log(tmp_path / "shim.log")
        if row["argv"][1:] == ["manage", "migrate", "--noinput"]
    ]
    assert rows
    assert rows[0]["data_dir"] == f"{here}/logstashui_data"


# acceptance #6
def test_upgrade_migrate_preserves_preset_env(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    shim = write_shim(tmp_path / "shims")
    plant_venv(Path(here_of(script)) / ".venv", shim)
    custom = str(tmp_path / "preset-data")
    env = env_for(
        tmp_path,
        tools_dir(tmp_path),
        path_prefix=str(shim.parent),
        python=str(shim),
        data_dir=custom,
    )
    archive = tmp_path / "archive"
    make_wheels(archive)
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = [
        row
        for row in read_log(tmp_path / "shim.log")
        if row["argv"][1:] == ["manage", "migrate", "--noinput"]
    ]
    assert rows
    assert rows[0]["data_dir"] == custom


# acceptance #6
def test_upgrade_nested_wheels_zip(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    import zipfile

    zpath = tmp_path / "logstashui-1.2.3-offline-wheels-linux-x86_64-cp312.zip"
    nested = "logstashui-1.2.3-offline-wheels-linux-x86_64-cp312/wheels/dummy.whl"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(nested, b"wheel")
    proc = run(script, ["--upgrade", str(zpath)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = read_log(tmp_path / "shim.log")
    extracted = [row for row in rows if row["argv"][1:4] == ["-m", "zipfile", "-e"]]
    assert len(extracted) == 1
    assert extracted[0]["argv"][4] == str(zpath)
    temp = extracted[0]["argv"][5]
    pip = pip_rows(rows)
    assert pip
    find_links = pip[0]["argv"][pip[0]["argv"].index("--find-links") + 1]
    assert find_links == f"{temp}/logstashui-1.2.3-offline-wheels-linux-x86_64-cp312/wheels"


# acceptance #6
def test_upgrade_nested_wheels_dir(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    archive = tmp_path / "archive"
    nested = archive / "logstashui-9-offline-wheels-linux-x86_64-cp312" / "wheels"
    nested.mkdir(parents=True)
    (nested / "dummy.whl").write_bytes(b"wheel")
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    pip = pip_rows(read_log(tmp_path / "shim.log"))
    assert pip
    find_links = pip[0]["argv"][pip[0]["argv"].index("--find-links") + 1]
    assert find_links == str(nested)


# acceptance #6
def test_upgrade_missing_wheels(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    import zipfile

    empty_dir = tmp_path / "empty-dir"
    empty_dir.mkdir()
    (empty_dir / "readme.txt").write_text("no wheels", encoding="utf-8")
    zpath = tmp_path / "invalid.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("readme.txt", b"no wheels")
    for target in (str(empty_dir), str(zpath)):
        log = tmp_path / "shim.log"
        log.write_text("", encoding="utf-8")
        proc = run(script, ["--upgrade", target], env, other_cwd(tmp_path))
        assert proc.returncode == 1, target
        assert "missing wheels directory" in proc.stderr
        assert pip_rows(read_log(log)) == []


# acceptance #6
def test_upgrade_preserves_data_sentinel(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    here = here_of(script)
    data = Path(here) / "logstashui_data"
    data.mkdir()
    sentinel = data / "sentinel"
    payload = b"sentinel-v1\n"
    sentinel.write_bytes(payload)
    archive = tmp_path / "archive"
    make_wheels(archive)
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert sentinel.read_bytes() == payload
    rows = read_log(tmp_path / "shim.log")
    pip = pip_rows(rows)
    migrate = [row for row in rows if row["argv"][1:] == ["manage", "migrate", "--noinput"]]
    assert pip and migrate
    argv = pip[0]["argv"]
    assert argv[argv.index("--upgrade-strategy") + 1] == "eager"
    assert migrate[0]["argv"][-1] == "--noinput"
