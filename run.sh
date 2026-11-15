#!/usr/bin/env bash
# =============================================================================
# run.sh — convenience wrapper around convert_and_clone.py
#
# Usage:
#   ./run.sh --input my_voice.m4a --text "Hello world"
#   ./run.sh --input me.m4a --text "Faster please" --steps 16 --speed 1.1
#   ./run.sh --input me.m4a --text "Hi"  --output greeting.wav
#
# This script:
#   1. Locates the omnivoice_env venv next to itself
#   2. Activates it
#   3. Forwards every CLI arg verbatim to convert_and_clone.py
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/omnivoice_env"
PY_APP="${SCRIPT_DIR}/convert_and_clone.py"

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}[FAIL]${NC} Virtual env not found at: $VENV_DIR"
    echo -e "       Run setup first:  ${GRN}./setup_omnivoice.sh${NC}"
    exit 1
fi

if [ ! -f "$PY_APP" ]; then
    echo -e "${RED}[FAIL]${NC} convert_and_clone.py missing next to run.sh."
    exit 1
fi

# Activate venv (relax `set -u` only for the activate script).
set +u
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
set -u

# Forward all args; preserve quoting via "$@".
exec python "$PY_APP" "$@"
