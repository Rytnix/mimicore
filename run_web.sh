#!/usr/bin/env bash
# Launch the VoiceClone Studio web UI.
#
# Usage:
#   ./run_web.sh          # build frontend (if missing) and serve via FastAPI on :8000
#   ./run_web.sh dev      # run Vite + FastAPI together for hot-reload (UI on :5173)
#   ./run_web.sh build    # only build the frontend
#
# Requires: omnivoice_env (created by setup_omnivoice.sh) and node/npm.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/omnivoice_env"
WEB="$ROOT/web"

if [[ ! -d "$VENV" ]]; then
  echo "omnivoice_env not found. Run ./setup_omnivoice.sh first." >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# If a local node tarball exists in .tools/, prepend it to PATH.
if [[ -x "$ROOT/.tools/node/bin/node" ]]; then
  export PATH="$ROOT/.tools/node/bin:$PATH"
fi

# faster-whisper / ctranslate2 needs CUDA 12 cublas+cudnn. The omnivoice venv
# has those installed as nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels; expose
# them to the dynamic linker BEFORE Python loads ctranslate2.
SITE_PKGS="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
for sub in nvidia/cublas/lib nvidia/cudnn/lib nvidia/cuda_nvrtc/lib; do
  d="$SITE_PKGS/$sub"
  [[ -d "$d" ]] && export LD_LIBRARY_PATH="$d:${LD_LIBRARY_PATH:-}"
done

# Make sure server-side Python deps are installed (uv if available, pip fallback).
ensure_py_deps() {
  python -c "import fastapi, uvicorn, faster_whisper, multipart, websockets" 2>/dev/null && return 0
  echo "[setup] installing missing Python deps..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$(which python)" fastapi 'uvicorn[standard]' python-multipart faster-whisper websockets
  else
    python -m pip install --quiet uv && \
      uv pip install --python "$(which python)" fastapi 'uvicorn[standard]' python-multipart faster-whisper websockets
  fi
}

ensure_node() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found. Install Node 20+ (e.g. 'sudo apt install nodejs npm') and re-run." >&2
    exit 1
  fi
}

build_frontend() {
  ensure_node
  pushd "$WEB" >/dev/null
  if [[ ! -d node_modules ]]; then
    echo "[setup] npm install..."
    npm install --no-audit --no-fund --silent
  fi
  echo "[setup] vite build..."
  npm run build --silent
  popd >/dev/null
}

cmd="${1:-serve}"

# Has any source file changed since the last build? (Skip rebuild only when
# dist is strictly newer than every src/index.html/vite config file.)
needs_rebuild() {
  [[ ! -d "$WEB/dist" ]] && return 0
  local stamp="$WEB/dist/index.html"
  [[ ! -f "$stamp" ]] && return 0
  # find anything newer than the stamp; if find prints anything, we rebuild.
  if find "$WEB/src" "$WEB/index.html" "$WEB/vite.config.js" "$WEB/package.json" \
        -newer "$stamp" -print -quit 2>/dev/null | grep -q .; then
    return 0
  fi
  return 1
}

case "$cmd" in
  build)
    ensure_py_deps
    build_frontend
    ;;
  dev)
    ensure_py_deps
    ensure_node
    pushd "$WEB" >/dev/null
    [[ -d node_modules ]] || npm install --no-audit --no-fund --silent
    popd >/dev/null
    echo "[dev] starting Vite on :5173 and FastAPI on :8000"
    ( cd "$WEB" && npm run dev ) &
    VITE_PID=$!
    trap 'kill $VITE_PID 2>/dev/null || true' EXIT
    python -m uvicorn server:app --host 0.0.0.0 --port 8002 --reload
    ;;
  serve|"")
    ensure_py_deps
    if needs_rebuild; then
      echo "[serve] frontend sources changed — rebuilding..."
      build_frontend
    else
      echo "[serve] frontend up-to-date — skipping rebuild (use './run_web.sh build' to force)"
    fi
    echo "[serve] http://localhost:8000"
    exec python -m uvicorn server:app --host 0.0.0.0 --port 8002
    ;;
  *)
    echo "Usage: $0 [serve|dev|build]" >&2
    exit 1
    ;;
esac
