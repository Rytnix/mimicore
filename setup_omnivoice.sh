#!/usr/bin/env bash
# =============================================================================
# setup_omnivoice.sh
# One-shot installer for the OmniVoice voice-cloning environment.
#
# Steps:
#   1. Verify Python 3.10+ (install via apt if missing)
#   2. Verify ffmpeg (install via apt if missing)
#   3. Verify NVIDIA GPU + driver via nvidia-smi
#   4. Bootstrap `uv` (Astral's fast parallel installer); fall back to pip
#   5. Create venv `omnivoice_env` with uv
#   6. Install PyTorch (CUDA 13 first, fall back to 12.x)
#   7. Install OmniVoice
#   8. Smoke-test imports
#
# Usage:  chmod +x setup_omnivoice.sh && ./setup_omnivoice.sh
# =============================================================================

set -euo pipefail

# ----- ANSI colors -----------------------------------------------------------
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

ok()    { echo -e "${GRN}[OK]${NC}    $*"; }
info()  { echo -e "${BLU}[INFO]${NC}  $*"; }
warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*" >&2; }

die()   { fail "$*"; exit 1; }

# `set -e` catches unhandled failures; map them to a friendly message.
trap 'fail "Setup aborted on line $LINENO. Scroll up for the underlying error."' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/omnivoice_env"

echo -e "${BLU}========================================================${NC}"
echo -e "${BLU}  OmniVoice setup — Linux + NVIDIA GPU                  ${NC}"
echo -e "${BLU}========================================================${NC}"

# ----- 1. Python 3.10+ -------------------------------------------------------
info "Checking for Python 3.10+ ..."
PY_BIN=""
for cand in python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        VER=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
        MAJ=${VER%.*}; MIN=${VER#*.}
        if [ "$MAJ" -ge 3 ] && [ "$MIN" -ge 10 ]; then
            PY_BIN="$cand"
            ok "Found $PY_BIN (version $VER)"
            break
        fi
    fi
done

if [ -z "$PY_BIN" ]; then
    warn "No Python 3.10+ found. Attempting apt install (requires sudo)."
    if ! command -v apt-get >/dev/null 2>&1; then
        die "apt-get not found. Install Python 3.10+ manually and re-run."
    fi
    sudo apt-get update
    sudo apt-get install -y python3.10 python3.10-venv python3.10-dev \
        || die "apt failed to install python3.10. On older Ubuntu, add the deadsnakes PPA: sudo add-apt-repository ppa:deadsnakes/ppa"
    PY_BIN="python3.10"
    ok "Installed $PY_BIN"
fi

# Make sure the venv module is present for whichever interpreter we picked.
if ! "$PY_BIN" -c 'import venv' >/dev/null 2>&1; then
    warn "venv module missing for $PY_BIN. Installing ${PY_BIN}-venv ..."
    sudo apt-get install -y "${PY_BIN}-venv" \
        || die "Could not install ${PY_BIN}-venv. Install it manually."
fi

# ----- 2. ffmpeg -------------------------------------------------------------
info "Checking for ffmpeg ..."
if command -v ffmpeg >/dev/null 2>&1; then
    ok "ffmpeg present: $(ffmpeg -version | head -1)"
else
    warn "ffmpeg not found. Installing via apt (needed for .m4a → .wav)."
    sudo apt-get update
    sudo apt-get install -y ffmpeg \
        || die "apt failed to install ffmpeg. Install manually: sudo apt install ffmpeg"
    ok "ffmpeg installed"
fi

# ----- 3. NVIDIA GPU ---------------------------------------------------------
info "Checking for NVIDIA GPU ..."
if ! command -v nvidia-smi >/dev/null 2>&1; then
    fail "nvidia-smi not found."
    fail "  - Confirm you have an NVIDIA GPU."
    fail "  - Install the proprietary driver, e.g.:  sudo ubuntu-drivers autoinstall"
    fail "  - Reboot, then re-run this script."
    exit 1
fi

if ! nvidia-smi >/dev/null 2>&1; then
    fail "nvidia-smi exists but failed to run. The kernel module is likely not loaded."
    fail "  Try:  sudo modprobe nvidia   (or reboot after a driver install)"
    exit 1
fi

GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
ok "Detected GPU: ${GPU_NAME}"

# ----- 4. Bootstrap uv (preferred) -------------------------------------------
# uv = Astral's Rust-based installer. Resolves and downloads packages in
# parallel, an order of magnitude faster than pip on cold caches. We use it
# for all subsequent installs and only fall back to pip if uv can't be
# obtained (e.g. no network for the official installer).
INSTALLER="uv"

if ! command -v uv >/dev/null 2>&1; then
    info "uv not found — installing via the official installer ..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh \
            || warn "uv installer script failed; will try pip-based bootstrap."
    fi
    # The installer drops the binary in ~/.local/bin or ~/.cargo/bin.
    export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
fi

if ! command -v uv >/dev/null 2>&1; then
    warn "Falling back: bootstrapping uv via pip into the user site."
    "$PY_BIN" -m pip install --user --quiet uv || true
    export PATH="$("$PY_BIN" -c 'import site; print(site.getuserbase())')/bin:${PATH}"
fi

if command -v uv >/dev/null 2>&1; then
    ok "uv ready: $(uv --version)"
else
    warn "uv unavailable — falling back to pip (slower)."
    INSTALLER="pip"
fi

# Wrapper so the rest of the script doesn't care which installer is active.
# Usage:  pip_install <pip-style args...>
pip_install() {
    if [ "$INSTALLER" = "uv" ]; then
        uv pip install "$@"
    else
        python -m pip install "$@"
    fi
}

# ----- 5. Virtual environment ------------------------------------------------
if [ -d "$VENV_DIR" ]; then
    warn "Existing venv at $VENV_DIR — reusing it. Delete it to start fresh."
else
    info "Creating venv at $VENV_DIR ..."
    if [ "$INSTALLER" = "uv" ]; then
        uv venv "$VENV_DIR" --python "$PY_BIN" || die "uv venv creation failed."
    else
        "$PY_BIN" -m venv "$VENV_DIR" || die "venv creation failed."
    fi
    ok "venv created"
fi

# Activate for the rest of this script. `set -u` blocks unbound vars in the
# activate script unless we briefly relax it.
set +u
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
set -u

# uv pip uses the active venv automatically (VIRTUAL_ENV is set by activate).
# For the pip fallback path we need pip itself inside the venv.
if [ "$INSTALLER" = "pip" ]; then
    info "Upgrading pip / wheel / setuptools inside the venv ..."
    python -m pip install --upgrade pip wheel setuptools >/dev/null
    ok "pip $(pip --version | awk '{print $2}') ready"
fi

# ----- 6. PyTorch (try newest CUDA wheel, fall back through older tags) ------
# We deliberately do NOT pin the torch version: PyTorch periodically drops
# old point releases from its index, so a hard pin (e.g. 2.8.0+cu128) will
# break a working install the moment that wheel ages out. We instead pin the
# CUDA tag and let the installer pick the newest matching wheel.
#
# `--index-url` (not --extra-index-url) forces resolution to use ONLY the
# PyTorch repo for this step, which guarantees we get the +cuXYZ local-
# version wheel and never accidentally fall through to a CPU build on PyPI.
install_torch() {
    local cu_tag="$1"
    info "Installing torch / torchaudio from PyTorch ${cu_tag} index (via ${INSTALLER}) ..."
    pip_install --index-url "https://download.pytorch.org/whl/${cu_tag}" \
        torch torchaudio
}

# Preference order: CUDA 13 first (per user request), then 12.x fallbacks.
TORCH_CUDA_TAGS=(cu130 cu128 cu126 cu124)
TORCH_OK=0
for cu_tag in "${TORCH_CUDA_TAGS[@]}"; do
    if install_torch "$cu_tag"; then
        TORCH_OK=1
        ok "PyTorch installed from ${cu_tag} channel"
        break
    fi
    warn "${cu_tag} wheels unavailable — trying the next CUDA tag."
done
if [ "$TORCH_OK" -ne 1 ]; then
    die "All PyTorch CUDA channels (${TORCH_CUDA_TAGS[*]}) failed.\n  Check your network, then visit https://pytorch.org/get-started/locally/ for the current install command."
fi

# ----- 7. OmniVoice ----------------------------------------------------------
info "Installing OmniVoice from PyPI (via ${INSTALLER}) ..."
pip_install omnivoice \
    || die "OmniVoice install failed. If HuggingFace is unreachable, try: HF_ENDPOINT=https://hf-mirror.com ./setup_omnivoice.sh"
ok "OmniVoice installed"

# ----- 8. Smoke test ---------------------------------------------------------
info "Verifying imports ..."
python - <<'PY' || die "Import smoke test failed. See traceback above."
import sys
try:
    import torch
    import torchaudio  # noqa: F401
    import omnivoice   # noqa: F401
except Exception as e:
    print(f"IMPORT ERROR: {e}", file=sys.stderr)
    raise

print(f"  torch       : {torch.__version__}")
print(f"  CUDA build  : {torch.version.cuda}")
print(f"  CUDA usable : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  GPU         : {torch.cuda.get_device_name(0)}")
PY
ok "All imports OK"

# ----- Done ------------------------------------------------------------------
echo
echo -e "${GRN}========================================================${NC}"
echo -e "${GRN}  Setup complete.                                       ${NC}"
echo -e "${GRN}========================================================${NC}"
echo -e "Next steps:"
echo -e "  1) Copy your iPhone Voice Memo (.m4a) into this folder."
echo -e "  2) Run the cloner:"
echo -e "       ${BLU}./run.sh --input my_voice.m4a --text \"Hello, world.\"${NC}"
echo -e "  3) Play the result:"
echo -e "       ${BLU}aplay cloned_output.wav${NC}   (or: vlc cloned_output.wav)"
echo
