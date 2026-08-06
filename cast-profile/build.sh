#!/bin/bash
# Stub build.sh for testing CAST's solver_dir/build_script fork interface
# (see manchester-fme/CAST .github/workflows/build.yml). Skips the real cvc5
# compile - the point of this script is only to prove that CAST resolved
# build_script/solver_dir to this file instead of its own src/solvers/cvc5,
# not to produce a working cvc5 binary.
# Usage: ./build.sh [--coverage] [--static]

set -e

echo "cast-profile stub build.sh invoked with args: $*"
echo "cwd: $(pwd)"

mkdir -p cvc5/build/bin
cat > cvc5/build/bin/cvc5 <<'EOF'
#!/bin/sh
echo "cvc5 stub binary from cast-profile smoke test (not a real build)"
EOF
chmod +x cvc5/build/bin/cvc5

echo "stub build complete: cvc5/build/bin/cvc5"
