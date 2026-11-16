#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# acceptance #6
import json
import os
import pwd
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packaging" / "offline" / "logstashui_local.sh"

# An absolute interpreter the shim can run under, whatever PATH holds.
BASE_PYTHON = sys.executable

# Deterministic candidate shim. `-c` runs the caller's code as the shim's own
# code object, with sys.version_info rewritten to a non-3.12 value, so the
# script's real version predicate is what rejects it (a shim that just exits 1
# would hide a broken predicate). `-m venv` / `-m pip` / `-m zipfile` are faked
# and logged. argv[0] is logged verbatim so callers can pin it.
SHIM = """#!@PYTHON@
import json
import os
import shutil
import sys
import types
import zipfile

def log():
    rec = {"argv": sys.argv, "path": os.environ.get("PATH"), "data_dir": os.environ.get("LOGSTASHUI_DATA_DIR")}
    with open(os.environ["SHIM_LOG"], "a", encoding="utf-8") as fh:
        print(json.dumps(rec), file=fh)

args = sys.argv[1:]
if args[:1] == ["-c"]:
    log()
    code = args[1]
    if "resolve_data_dir" in code:
        # The product's data-dir resolver: run the REAL module so the resolved
        # path is the application's own answer, not a test-side guess.
        sys.path.insert(0, os.environ["SHIM_SRC"])
        from LogstashUI.paths import resolve_data_dir

        print(resolve_data_dir(migrate_legacy=False))
        sys.exit(0)
    fake = (3, @MINOR@, 0, "final", 0)

    class FakeVersion:
        major, minor, micro, releaselevel, serial = fake

        def __getitem__(self, k):
            return fake[k]

        def __len__(self):
            return len(fake)

    sys.version_info = FakeVersion()
    sys.maxsize = @MAXSIZE@
    sys.implementation = types.SimpleNamespace(name="@IMPL@")
    # The product's validation imports platform and asks it the machine name;
    # a module-level stub is what makes the architecture faked rather than the
    # host's real x86_64 answering for every candidate.
    platform_mod = types.ModuleType("platform")
    platform_mod.machine = lambda: "@MACHINE@"
    sys.modules["platform"] = platform_mod
    exec(compile(code, "<shim>", "exec"), {"__name__": "__main__"})
    sys.exit(0)
if args[:2] == ["-m", "venv"]:
    log()
    dest = args[-1]
    bindir = os.path.join(dest, "bin")
    os.makedirs(bindir, exist_ok=True)
    for name in ("python", "logstashui"):
        target = os.path.join(bindir, name)
        shutil.copy2(os.path.abspath(sys.argv[0]), target)
        os.chmod(target, os.stat(target).st_mode | 0o111)
    sys.exit(0)
if args[:2] == ["-m", "pip"]:
    log()
    bindir = os.path.dirname(os.path.abspath(sys.argv[0]))
    dest = os.path.join(bindir, "logstashui")
    shutil.copy2(os.path.abspath(sys.argv[0]), dest)
    os.chmod(dest, os.stat(dest).st_mode | 0o111)
    sys.exit(0)
if args[:3] == ["-m", "zipfile", "-e"]:
    zipfile.ZipFile(args[3]).extractall(args[4])
    log()
    sys.exit(0)
log()
sys.exit(0)
"""

TOOLS = ("dirname", "cat", "mktemp", "mkdir", "chmod", "rm", "cp")


def here_of(script: Path) -> str:
    out = subprocess.check_output(
        ["sh", "-c", 'CDPATH= cd -- "$(dirname "$1")" && pwd', "sh", str(script)],
        text=True,
    )
    return out.strip()


def tools_dir(tmp: Path) -> str:
    bindir = tmp / "tools"
    bindir.mkdir(exist_ok=True)
    for name in TOOLS:
        src = shutil.which(name)
        if not src:
            raise RuntimeError(f"missing tool {name}")
        if not (bindir / name).exists():
            os.symlink(src, bindir / name)
    return str(bindir)


def write_shim(
    directory: Path,
    name: str = "python3.12",
    minor: int = 11,
    maxsize: int = 2 ** 63 - 1,
    impl: str = "cpython",
    machine: str = "x86_64",
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        SHIM.replace("@PYTHON@", BASE_PYTHON)
        .replace("@MINOR@", str(minor))
        .replace("@MAXSIZE@", str(maxsize))
        .replace("@IMPL@", impl)
        .replace("@MACHINE@", machine)
    )
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
    wheels.mkdir(parents=True, exist_ok=True)
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
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def pip_rows(rows: list) -> list:
    return [row for row in rows if row["argv"][1:3] == ["-m", "pip"]]


def migrate_rows(rows: list) -> list:
    return [row for row in rows if row["argv"][1:] == ["manage", "migrate", "--noinput"]]


def env_for(tmp: Path, tools: str, *, path_prefix=None, python=None, data_dir=None) -> dict:
    parts = []
    if path_prefix:
        parts.append(str(path_prefix))
    parts.append(tools)
    env = {
        "PATH": ":".join(parts),
        "HOME": str(tmp),
        "TMPDIR": str(tmp),
        "SHIM_LOG": str(tmp / "shim.log"),
        # the shim imports the real LogstashUI package for the resolver probe
        "SHIM_SRC": str(ROOT / "src" / "logstashui"),
        "PYTHONPATH": str(ROOT / "src"),
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


def bundle_with_venv(tmp: Path, data_dir=None):
    bundle = tmp / "bundle"
    script = copy_script(bundle)
    here = Path(here_of(script))
    shim = write_shim(tmp / "shims")
    plant_venv(here / ".venv", shim)
    env = env_for(tmp, tools_dir(tmp), path_prefix=shim.parent, python=str(shim), data_dir=data_dir)
    return bundle, script, here, shim, env


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
    for part in env["PATH"].split(":"):
        for name in ("python", "python3", "python3.12"):
            assert not (Path(part) / name).exists()
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
    proc = run(script, ["--install"], env, other_cwd(tmp_path))
    assert proc.returncode == 1
    assert "need CPython 3.12 x86_64" in proc.stderr
    assert not (bundle / ".venv").exists()


# acceptance #6
def test_python_validation(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    make_wheels(bundle)
    tools = tools_dir(tmp_path)
    cwd = other_cwd(tmp_path)
    # one candidate per rejection category: version, implementation, the two
    # 64-bit ARM names, and 32-bit pointer size
    candidates = {
        "version": {"minor": 11},
        "implementation": {"minor": 12, "impl": "pypy"},
        "aarch64": {"minor": 12, "machine": "aarch64"},
        "arm64": {"minor": 12, "machine": "arm64"},
        "maxsize": {"minor": 12, "maxsize": 2 ** 32 - 1},
    }
    for label, kwargs in candidates.items():
        shim = write_shim(tmp_path / f"shims-{label}", **kwargs)
        for optimize in (None, "1"):
            env = env_for(tmp_path, tools, path_prefix=shim.parent, python=str(shim))
            if optimize:
                env["PYTHONOPTIMIZE"] = optimize
            proc = run(script, ["--install"], env, cwd)
            ctx = f"{label} PYTHONOPTIMIZE={optimize}"
            assert proc.returncode == 1, (ctx, proc.stdout, proc.stderr)
            assert "need CPython 3.12 x86_64" in proc.stderr, ctx
            assert not (bundle / ".venv").exists(), ctx
            assert pip_rows(read_log(tmp_path / "shim.log")) == [], ctx
    # the categories are distinct because the script's own code decides: each
    # faked value above is the only failing clause, so a py_ok replaced by
    # `sys.exit(0)` (or one missing any single clause) accepts a candidate here.


# acceptance #6
def test_python_precedence(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    make_wheels(bundle)
    chosen = write_shim(tmp_path / "chosen", "python", minor=12)
    on_path = write_shim(tmp_path / "onpath", "python3.12", minor=12)
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=on_path.parent, python=str(chosen))
    proc = run(script, ["--install"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = read_log(tmp_path / "shim.log")
    venv_rows = [row for row in rows if row["argv"][1:3] == ["-m", "venv"]]
    assert venv_rows
    assert all(row["argv"][0] == str(chosen) for row in venv_rows)
    assert all(row["argv"][0] != str(on_path) for row in rows)
    assert (bundle / ".venv").is_dir()


# acceptance #6
def test_install_missing_wheels(tmp_path):
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    shim = write_shim(tmp_path / "shims")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=shim.parent)
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
    shim = write_shim(tmp_path / "shims", minor=12)
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=shim.parent)
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
    shim = write_shim(tmp_path / "shims", minor=12)
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=shim.parent)
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
    here = Path(here_of(script))
    assert not (bundle / ".venv").exists()
    shim = write_shim(tmp_path / "shims", minor=12)
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=shim.parent)
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
    bundle, script, here, shim, env = bundle_with_venv(tmp_path)
    proc = run(script, ["--serve", "--bind", "127.0.0.1:8000"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = read_log(tmp_path / "shim.log")
    assert [f"{here}/.venv/bin/logstashui", "serve", "--bind", "127.0.0.1:8000"] in [
        row["argv"] for row in rows
    ]


# acceptance #6
def test_serve_exports_data_dir(tmp_path):
    bundle, script, here, shim, env = bundle_with_venv(tmp_path)
    assert "LOGSTASHUI_DATA_DIR" not in env
    proc = run(script, ["serve"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = [row for row in read_log(tmp_path / "shim.log") if row["argv"][1:] == ["serve"]]
    assert rows
    assert rows[0]["data_dir"] == f"{here}/logstashui_data"
    assert rows[0]["path"] == f"{here}/.venv/bin:{env['PATH']}"


# acceptance #6
def test_serve_install_path_exports_data_dir(tmp_path):
    script = copy_script(tmp_path / "bundle")
    install = tmp_path / "opt"
    shim = write_shim(tmp_path / "shims")
    plant_venv(install / ".venv", shim)
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=shim.parent, python=str(shim))
    proc = run(script, ["--install-path", str(install), "serve"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = [row for row in read_log(tmp_path / "shim.log") if row["argv"][1:] == ["serve"]]
    assert rows
    assert rows[0]["data_dir"] == f"{install}/logstashui_data"


# acceptance #6
def test_serve_preserves_custom_data_dir_env(tmp_path):
    custom = str(tmp_path / "custom data")
    bundle, script, here, shim, env = bundle_with_venv(tmp_path, data_dir=custom)
    proc = run(script, ["serve"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = [row for row in read_log(tmp_path / "shim.log") if row["argv"][1:] == ["serve"]]
    assert rows
    assert rows[0]["data_dir"] == custom


# acceptance #6
def test_serve_existing_venv_without_host_python(tmp_path):
    bundle, script, here, shim, env = bundle_with_venv(tmp_path)
    # no host python: drop the shim dir from PATH and unset PYTHON
    env["PATH"] = env["PATH"].split(":", 1)[1]
    env.pop("PYTHON", None)
    for part in env["PATH"].split(":"):
        for name in ("python", "python3", "python3.12"):
            assert not (Path(part) / name).exists()
    proc = run(script, ["serve"], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "need CPython 3.12 x86_64" not in proc.stderr
    rows = read_log(tmp_path / "shim.log")
    serve = [row for row in rows if row["argv"][1:] == ["serve"]]
    assert serve
    assert serve[0]["argv"] == [f"{here}/.venv/bin/logstashui", "serve"]
    assert serve[0]["path"].split(":")[0] == f"{here}/.venv/bin"
    assert pip_rows(rows) == []


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
    here = Path(here_of(script))
    plant_venv(here / ".venv", shim)
    live_pid(here / "logstashui_data" / "gunicorn.pid")
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=shim.parent, python=str(shim))
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
    env = env_for(tmp_path, tools_dir(tmp_path), path_prefix=shim.parent, python=str(shim))
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
    here = Path(here_of(script))
    plant_venv(here / ".venv", shim)
    tools = tools_dir(tmp_path)
    cwd = other_cwd(tmp_path)
    account = pwd.getpwuid(os.getuid())
    # a unique leaf under the real home of the account `~<name>` names
    named_dir = Path(account.pw_dir) / f"logstashui_data-s1-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    spaced = tmp_path / "spaced data"
    cases = {
        # leading tilde: $HOME is tmp_path in env_for
        "tilde": ("~/logstashui_data", tmp_path / "logstashui_data"),
        # named user home: only resolve_data_dir expands `~user`
        "named-user": (f"~{account.pw_name}/{named_dir.name}", named_dir),
        # absolute path padded with whitespace
        "padded": (f"  {spaced}  ", spaced),
    }
    try:
        for label, (preset, pid_dir) in cases.items():
            pid_dir.mkdir(parents=True, exist_ok=True)
            live_pid(pid_dir / "gunicorn.pid")
            log = tmp_path / f"shim-{label}.log"
            env = env_for(tmp_path, tools, path_prefix=shim.parent, python=str(shim), data_dir=preset)
            env["SHIM_LOG"] = str(log)
            proc = run(script, ["--upgrade", str(archive)], env, cwd)
            ctx = f"{label} preset={preset!r}"
            assert proc.returncode == 1, (ctx, proc.stdout, proc.stderr)
            assert "error: logstashui server is running. Stop server before upgrading." in proc.stderr, ctx
            assert pip_rows(read_log(log)) == [], ctx
            shutil.rmtree(pid_dir)
    finally:
        shutil.rmtree(named_dir, ignore_errors=True)


def _upgrade_ready(tmp: Path):
    bundle = tmp / "bundle"
    script = copy_script(bundle)
    shim = write_shim(tmp / "shims")
    plant_venv(Path(here_of(script)) / ".venv", shim)
    env = env_for(tmp, tools_dir(tmp), path_prefix=shim.parent, python=str(shim))
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
    migrate = migrate_rows(rows)
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
        f"{archive}/wheels",
        "--upgrade",
        "--upgrade-strategy",
        "eager",
        "LogstashUI[databases,otel]",
    ]
    assert migrate[0]["argv"] == [f"{here}/.venv/bin/logstashui", "manage", "migrate", "--noinput"]


# acceptance #6
def test_upgrade_migrate_exports_data_dir(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    here = here_of(script)
    archive = tmp_path / "archive"
    make_wheels(archive)
    assert "LOGSTASHUI_DATA_DIR" not in env
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = migrate_rows(read_log(tmp_path / "shim.log"))
    assert rows
    assert rows[0]["data_dir"] == f"{here}/logstashui_data"


# acceptance #6
def test_upgrade_migrate_preserves_preset_env(tmp_path):
    custom = str(tmp_path / "preset-data")
    bundle = tmp_path / "bundle"
    script = copy_script(bundle)
    shim = write_shim(tmp_path / "shims")
    plant_venv(Path(here_of(script)) / ".venv", shim)
    env = env_for(
        tmp_path,
        tools_dir(tmp_path),
        path_prefix=shim.parent,
        python=str(shim),
        data_dir=custom,
    )
    archive = tmp_path / "archive"
    make_wheels(archive)
    proc = run(script, ["--upgrade", str(archive)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rows = migrate_rows(read_log(tmp_path / "shim.log"))
    assert rows
    assert rows[0]["data_dir"] == custom


# acceptance #6
def test_upgrade_nested_wheels_zip(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    zpath = tmp_path / "logstashui-1.2.3-offline-wheels-linux-x86_64-cp312.zip"
    top = "logstashui-1.2.3-offline-wheels-linux-x86_64-cp312"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(f"{top}/wheels/dummy.whl", b"wheel")
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
    assert find_links == f"{temp}/{top}/wheels"


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
def test_upgrade_zip_without_host_python(tmp_path):
    script, env = _upgrade_ready(tmp_path)
    env["PATH"] = env["PATH"].split(":", 1)[1]
    env.pop("PYTHON", None)
    for part in env["PATH"].split(":"):
        for name in ("python", "python3", "python3.12"):
            assert not (Path(part) / name).exists()
    zpath = tmp_path / "logstashui-1.2.3-offline-wheels-linux-x86_64-cp312.zip"
    top = "logstashui-1.2.3-offline-wheels-linux-x86_64-cp312"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(f"{top}/wheels/dummy.whl", b"wheel")
    proc = run(script, ["--upgrade", str(zpath)], env, other_cwd(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "need CPython 3.12 x86_64" not in proc.stderr
    rows = read_log(tmp_path / "shim.log")
    extracted = [row for row in rows if row["argv"][1:4] == ["-m", "zipfile", "-e"]]
    assert extracted
    here = here_of(script)
    assert all(row["argv"][0] == f"{here}/.venv/bin/python" for row in extracted)
    pip = pip_rows(rows)
    assert pip
    find_links = pip[0]["argv"][pip[0]["argv"].index("--find-links") + 1]
    assert find_links == f"{extracted[0]['argv'][5]}/{top}/wheels"
    assert migrate_rows(rows)


# acceptance #6
def test_upgrade_missing_wheels(tmp_path):
    script, env = _upgrade_ready(tmp_path)
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
    data = Path(here_of(script)) / "logstashui_data"
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
    migrate = migrate_rows(rows)
    assert pip and migrate
    argv = pip[0]["argv"]
    assert argv[argv.index("--upgrade-strategy") + 1] == "eager"
    assert migrate[0]["argv"][-1] == "--noinput"
