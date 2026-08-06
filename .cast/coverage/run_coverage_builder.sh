#!/bin/bash
# Simple coverage analysis script for a test range

set -e

START_INDEX=$1
END_INDEX=$2

echo "Running coverage analysis for tests ${START_INDEX}-${END_INDEX}"

# Set test timeout environment variable (120 seconds = 2 minutes)
export TEST_TIMEOUT=120

# Resolve coverage_mapper.py relative to this script's own location, not a
# hardcoded CAST-internal path, so this profile stays portable if solver_dir
# points somewhere other than src/solvers/cvc5 (e.g. a fork's own checkout).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to build directory
cd cvc5/build

# Run coverage analysis
python3 "$SCRIPT_DIR/coverage_mapper.py" \
    --build-dir . \
    --start-index ${START_INDEX} \
    --end-index ${END_INDEX}

echo "Coverage analysis completed"
