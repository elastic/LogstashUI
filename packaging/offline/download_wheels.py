#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Download cp312 manylinux wheels. Pure-Python sdists are wheeled on the builder."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REQ_LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<ver>[^;\\\s]+)(?:\s*;\s*(?P<marker>.+))?$"
)


def parse_requirements(path: Path) -> list[tuple[str, str, str | None]]:
    pkgs: list[tuple[str, str, str | None]] = []
    pending = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        line = (pending + line).strip()
        pending = ""
        # Drop hash fragments pip export may still leave on the same line.
        line = re.sub(r"\s+--hash=\S+", "", line).strip()
        m = REQ_LINE.match(line)
        if not m:
            continue
        marker = (m.group("marker") or "").strip() or None
        pkgs.append((m.group("name"), m.group("ver"), marker))
    return pkgs


def pip(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pip", *args],
        text=True,
        capture_output=True,
    )


def is_linux_x86_wheel(name: str) -> bool:
    n = name.lower()
    if n.endswith(".tar.gz") or n.endswith(".zip"):
        return False
    if "macosx" in n or "win_amd64" in n or "win32" in n or "aarch64" in n:
        return False
    return n.endswith(".whl") and (
        "manylinux" in n or "linux_x86_64" in n or "none-any" in n
    )


PLATFORMS = (
    "manylinux2014_x86_64",
    "manylinux_2_28_x86_64",
)


def download_binary(name: str, ver: str, dest: Path) -> bool:
    spec = f"{name}=={ver}"
    common = [
        "download",
        spec,
        "-d",
        str(dest),
        "--no-deps",
        "--python-version",
        "3.12",
        "--only-binary",
        ":all:",
        "--disable-pip-version-check",
    ]
    for platform in PLATFORMS:
        proc = pip(*common, "--platform", platform)
        if proc.returncode == 0:
            return True
    # py3-none-any (no --platform): login-required-middleware 0.8 has a wheel; 0.9 does not.
    proc = pip(*common)
    return proc.returncode == 0


def wheel_sdist(name: str, ver: str, dest: Path) -> None:
    spec = f"{name}=={ver}"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        proc = pip(
            "download",
            spec,
            "-d",
            str(tmp_path),
            "--no-deps",
            "--no-binary",
            ":all:",
            "--disable-pip-version-check",
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            raise SystemExit(
                f"no manylinux cp312 wheel and sdist download failed for {spec}"
            )
        sdists = list(tmp_path.glob("*.tar.gz")) + list(tmp_path.glob("*.zip"))
        if not sdists:
            raise SystemExit(f"sdist missing after download for {spec}")
        proc = pip(
            "wheel",
            "--no-deps",
            "--no-cache-dir",
            "-w",
            str(tmp_path),
            str(sdists[0]),
            "--disable-pip-version-check",
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            raise SystemExit(f"could not build a wheel from sdist for {spec}")
        wheels = [p for p in tmp_path.glob("*.whl") if is_linux_x86_wheel(p.name)]
        if not wheels:
            built = list(tmp_path.glob("*.whl"))
            raise SystemExit(
                f"{spec} is sdist-only and built {built or 'no wheel'} "
                f"(need py3-none-any or manylinux x86_64). Freeze aborted."
            )
        target = dest / wheels[0].name
        target.write_bytes(wheels[0].read_bytes())
        print(f"built wheel from sdist: {wheels[0].name}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("requirements")
    parser.add_argument("dest")
    args = parser.parse_args()
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    pkgs = parse_requirements(Path(args.requirements))
    if not pkgs:
        raise SystemExit(f"no packages parsed from {args.requirements}")
    for name, ver, marker in pkgs:
        marker_norm = (marker or "").replace('"', "'")
        if "sys_platform == 'win32'" in marker_norm or "sys_platform == 'darwin'" in marker_norm:
            print(f"skip {name}=={ver} (marker {marker})", flush=True)
            continue
        spec = f"{name}=={ver}"
        print(f"download {spec}", flush=True)
        if download_binary(name, ver, dest):
            continue
        print(f"binary miss {spec}; trying sdist→wheel", flush=True)
        wheel_sdist(name, ver, dest)
    bad = [
        p.name
        for p in dest.iterdir()
        if p.is_file() and not is_linux_x86_wheel(p.name) and p.suffix != ".txt"
    ]
    # Allow the LogstashUI wheel already copied in (py3-none-any).
    leftover_sdists = list(dest.glob("*.tar.gz")) + list(dest.glob("*.zip"))
    if leftover_sdists:
        names = ", ".join(p.name for p in leftover_sdists)
        raise SystemExit(f"sdist left in wheelhouse: {names}")
    if bad:
        raise SystemExit(f"non-linux-x86_64 artifacts: {', '.join(bad)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
