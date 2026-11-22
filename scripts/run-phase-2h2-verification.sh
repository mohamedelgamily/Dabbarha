#!/bin/bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
work="$HOME/Documents/Codex/2026-10-21/files-pasted-by-the-user-you/work"
base="$work/batch6/implementation/secure-venv/bin/python"
scratch=$(mktemp -d "${TMPDIR:-/tmp}/dabbarha-2h2.XXXXXXXX")
echo "Isolated verification environment: $scratch"
"$base" -I -m venv "$scratch/venv"
python="$scratch/venv/bin/python"
# Match the audited verification toolchain in the new environment only.
pip_version=$("$base" -I -c 'from importlib.metadata import version; print(version("pip"))')
"$python" -I -m pip --isolated install --index-url https://pypi.org/simple "pip==$pip_version"
sed -n '/^dnspython==/{p;n;p;}' requirements-linux-py312.lock > "$scratch/dns.txt"
"$python" -I -m pip --isolated install --index-url https://pypi.org/simple --only-binary=:all: --no-deps --require-hashes -r "$scratch/dns.txt"
"$python" -I -m pip --isolated install --index-url https://pypi.org/simple -r requirements.txt -r constraints-python312.txt
VERIFY_PYTHON="$python" bash scripts/run-phase-2h1-verification.sh
