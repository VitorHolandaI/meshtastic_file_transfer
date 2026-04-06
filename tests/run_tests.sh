#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="$ROOT_DIR/../.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: venv not found at $PYTHON"
    exit 1
fi

LAYER="${1:-all}"

run_layer() {
    local pattern="$1"
    local label="$2"
    echo ""
    echo "========================================"
    echo " $label"
    echo "========================================"
    "$PYTHON" -m unittest discover -s "$SCRIPT_DIR" -p "$pattern" -v 2>&1 \
        | grep -E "(test_|ERROR|FAIL|OK|Ran)" || true
}

case "$LAYER" in
    1)
        run_layer "test_layer1*" "Layer 1 — Protocol serialization"
        ;;
    2)
        run_layer "test_layer2*" "Layer 2 — Protocol logic (mocks)"
        ;;
    all)
        run_layer "test_layer1*" "Layer 1 — Protocol serialization"
        run_layer "test_layer2*" "Layer 2 — Protocol logic (mocks)"
        ;;
    *)
        echo "Usage: $0 [1|2|all]"
        exit 1
        ;;
esac

echo ""
echo "========================================"
echo " Done"
echo "========================================"
