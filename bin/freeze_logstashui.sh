#!/bin/bash
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

# Optional air-gapped freeze. Default `uv build` is unchanged.
# Usage:
#   ./bin/freeze_logstashui.sh [--wheels] [--docker] [--standalone] [--all]
#                              [--output DIR] [--image NAME]
# No artifact flags → --all.

set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
TEMPLATES="$ROOT/packaging/offline"
DO_WHEELS=0
DO_DOCKER=0
DO_STANDALONE=0
EXPLICIT_STANDALONE=0
OUT=""
IMAGE_OVERRIDE=""

usage() {
    cat <<'EOF'
Usage: freeze_logstashui.sh [--wheels] [--docker] [--standalone] [--all]
                            [--output DIR] [--image NAME]

Connected-builder freeze for air-gapped hosts. Default uv build is unchanged.

  --wheels       CPython 3.12 manylinux x86_64 wheelhouse zip
  --docker       docker save of a local image (never docker pull)
  --standalone   experimental PyInstaller onedir (Linux x86_64 only)
  --all          all three (default if no artifact flags)
  --output DIR   default: <repo>/dist/offline
  --image NAME   docker save this local tag instead of building

Isolated wheels host: CPython 3.12 x86_64 + python3.12-venv. No uv.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wheels) DO_WHEELS=1 ;;
        --docker) DO_DOCKER=1 ;;
        --standalone) DO_STANDALONE=1; EXPLICIT_STANDALONE=1 ;;
        --all) DO_WHEELS=1; DO_DOCKER=1; DO_STANDALONE=1 ;;
        --output)
            OUT="${2:?--output requires a directory}"
            shift
            ;;
        --image)
            IMAGE_OVERRIDE="${2:?--image requires a name}"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
    shift
done

if [[ $DO_WHEELS -eq 0 && $DO_DOCKER -eq 0 && $DO_STANDALONE -eq 0 ]]; then
    DO_WHEELS=1
    DO_DOCKER=1
    DO_STANDALONE=1
fi

OUT="${OUT:-$ROOT/dist/offline}"
mkdir -p "$OUT"

die() { echo "ERROR: $*" >&2; exit 1; }

version_from_pyproject() {
    sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml" | head -n 1
}

subst() {
    # $1 src  $2 dest
    local git_sha="$GIT_SHA"
    local version="$VERSION"
    local image="$IMAGE_NAME"
    sed \
        -e "s|__VERSION__|${version}|g" \
        -e "s|__GIT_SHA__|${git_sha}|g" \
        -e "s|__IMAGE_NAME__|${image}|g" \
        "$1" > "$2"
}

sha256_tree() {
    local dir="$1"
    local out="$2"
    (
        cd "$dir"
        if command -v sha256sum >/dev/null 2>&1; then
            find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum
        else
            find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 shasum -a 256
        fi
    ) > "$out"
}

zip_dir() {
    local src="$1"
    local dest="$2"
    rm -f "$dest"
    (
        cd "$(dirname "$src")"
        zip -r -q "$dest" "$(basename "$src")"
    )
}

require_uv() {
    command -v uv >/dev/null 2>&1 || die "uv is required. Install: https://docs.astral.sh/uv/getting-started/installation/"
    uv python find 3.12 >/dev/null 2>&1 || die "Need CPython 3.12 (uv python install 3.12)"
    command -v zip >/dev/null 2>&1 || die "zip is required to pack freeze artifacts"
}

ensure_tailwind() {
    local css="$ROOT/src/logstashui/theme/static/css/dist/styles.css"
    if [[ -s "$css" ]]; then
        return 0
    fi
    command -v npm >/dev/null 2>&1 || die "Tailwind CSS missing and npm is not installed"
    (cd "$ROOT/src/logstashui/theme/static_src" && npm install && npm run build)
    [[ -s "$css" ]] || die "Tailwind CSS build did not produce $css"
}

linux_x86_64() {
    [[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]]
}

freeze_wheels() {
    local stage="$OUT/logstashui-${VERSION}-offline-wheels-linux-x86_64-cp312"
    local wheels="$stage/wheels"
    local req="$OUT/requirements-offline.txt"
    local zip="$OUT/logstashui-${VERSION}-offline-wheels-linux-x86_64-cp312.zip"

    rm -rf "$stage"
    mkdir -p "$wheels"

    echo "==> uv build (normal wheel)"
    (cd "$ROOT" && uv build)

    local whl
    whl=$(ls -1 "$ROOT/dist"/logstashui-"${VERSION}"-*.whl 2>/dev/null | head -n 1 || true)
    [[ -n "$whl" && -f "$whl" ]] || die "uv build did not produce dist/logstashui-${VERSION}-*.whl"
    cp "$whl" "$wheels/"

    echo "==> uv export --frozen --extra databases"
    (cd "$ROOT" && uv export --frozen --no-dev --extra databases --no-emit-project \
        -o "$req" >/dev/null)
    local req_plain="$OUT/requirements-offline.nohash.txt"
    (cd "$ROOT" && uv export --frozen --no-dev --extra databases --no-emit-project --no-hashes \
        -o "$req_plain" >/dev/null)

    echo "==> download manylinux cp312 wheels (pure-python sdists → wheel on builder)"
    (cd "$ROOT" && uv run --python 3.12 --with pip python \
        "$TEMPLATES/download_wheels.py" "$req_plain" "$wheels")

    subst "$TEMPLATES/wheels-install.sh" "$stage/install.sh"
    subst "$TEMPLATES/wheels-README.md" "$stage/README.md"
    chmod +x "$stage/install.sh"
    cp "$ROOT/LICENSE.txt" "$stage/LICENSE.txt"
    cp "$ROOT/NOTICE.txt" "$stage/NOTICE.txt"
    cp "$req" "$stage/requirements-offline.txt"

    {
        echo "LogstashUI ${VERSION}"
        echo "git ${GIT_SHA}"
        echo "python CPython 3.12"
        echo "platform linux-x86_64"
        echo "extra databases"
        echo
        echo "wheels:"
        (cd "$wheels" && ls -1 *.whl | sort)
    } > "$stage/MANIFEST.txt"

    sha256_tree "$stage" "$stage/SHA256SUMS.txt"
    zip_dir "$stage" "$zip"
    echo "Wrote $zip"
}

freeze_docker() {
    local tag="${IMAGE_OVERRIDE:-logstashui:offline-${VERSION}}"
    IMAGE_NAME="$tag"
    local stage="$OUT/logstashui-${VERSION}-offline-docker-linux-x86_64"
    local zip="$OUT/logstashui-${VERSION}-offline-docker-linux-x86_64.zip"

    command -v docker >/dev/null 2>&1 || die "docker is required for --docker"

    if [[ -n "$IMAGE_OVERRIDE" ]]; then
        docker image inspect "$IMAGE_OVERRIDE" >/dev/null 2>&1 \
            || die "image ${IMAGE_OVERRIDE} is not local (never docker pull). Build it or omit --image."
    else
        echo "==> docker build --platform linux/amd64 ${tag}"
        docker build --platform linux/amd64 -f "$ROOT/docker/Dockerfile" -t "$tag" "$ROOT"
    fi

    rm -rf "$stage"
    mkdir -p "$stage"
    echo "==> docker save ${tag}"
    docker save "$tag" | gzip -c > "$stage/image.tar.gz"

    subst "$TEMPLATES/docker-load.sh" "$stage/load.sh"
    subst "$TEMPLATES/docker-README.md" "$stage/README.md"
    subst "$TEMPLATES/compose.offline.yml" "$stage/compose.offline.yml"
    chmod +x "$stage/load.sh"
    cp "$ROOT/LICENSE.txt" "$stage/LICENSE.txt"
    cp "$ROOT/NOTICE.txt" "$stage/NOTICE.txt"
    sha256_tree "$stage" "$stage/SHA256SUMS.txt"
    zip_dir "$stage" "$zip"
    echo "Wrote $zip"
}

freeze_standalone() {
    if ! linux_x86_64; then
        if [[ "$EXPLICIT_STANDALONE" -eq 1 ]]; then
            die "standalone freeze requires Linux x86_64 (PyInstaller binary is per-OS)"
        fi
        echo "WARNING: skipping --standalone (not Linux x86_64)" >&2
        return 0
    fi

    local venv="$OUT/.standalone-venv"
    local work="$OUT/pyinstaller-work"
    local dist="$OUT/pyinstaller-dist"
    local stage="$OUT/logstashui-${VERSION}-offline-standalone-linux-x86_64"
    local zip="$OUT/logstashui-${VERSION}-offline-standalone-linux-x86_64.zip"
    echo "==> throwaway venv + PyInstaller (not a project dependency)"
    rm -rf "$venv" "$work" "$dist"
    uv venv --python 3.12 "$venv"
    (cd "$ROOT" && uv pip install --python "$venv" ".[databases]")
    uv pip install --python "$venv" pyinstaller
    "$venv/bin/pyinstaller" \
        --noconfirm \
        --clean \
        --workpath "$work" \
        --distpath "$dist" \
        "$TEMPLATES/logstashui.spec"

    [[ -x "$dist/logstashui/logstashui" ]] || die "PyInstaller did not produce $dist/logstashui/logstashui"

    rm -rf "$stage"
    mkdir -p "$stage"
    cp -a "$dist/logstashui" "$stage/logstashui"
    subst "$TEMPLATES/standalone-run.sh" "$stage/run.sh"
    subst "$TEMPLATES/standalone-README.md" "$stage/README.md"
    chmod +x "$stage/run.sh"
    cp "$ROOT/LICENSE.txt" "$stage/LICENSE.txt"
    cp "$ROOT/NOTICE.txt" "$stage/NOTICE.txt"
    sha256_tree "$stage" "$stage/SHA256SUMS.txt"
    zip_dir "$stage" "$zip"
    echo "Wrote $zip"
}

VERSION=$(version_from_pyproject)
[[ -n "$VERSION" ]] || die "could not read version from pyproject.toml"
GIT_SHA=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)
IMAGE_NAME="${IMAGE_OVERRIDE:-logstashui:offline-${VERSION}}"

require_uv
ensure_tailwind

echo "LogstashUI ${VERSION}  git ${GIT_SHA}  output ${OUT}"

if [[ $DO_WHEELS -eq 1 ]]; then
    freeze_wheels
fi
if [[ $DO_DOCKER -eq 1 ]]; then
    freeze_docker
fi
if [[ $DO_STANDALONE -eq 1 ]]; then
    freeze_standalone
fi
