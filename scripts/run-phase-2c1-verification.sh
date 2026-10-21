#!/bin/bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
: "${VERIFY_PYTHON:?Set VERIFY_PYTHON to the CPython 3.12 verification interpreter}"
: "${REDIS_SERVER_BINARY:?Set REDIS_SERVER_BINARY to the disposable Redis 7.4.11 binary}"
: "${POSTGRES_TEST_BIN:?Set POSTGRES_TEST_BIN to the disposable PostgreSQL 18.6 bin directory}"
: "${PIP_AUDIT_BIN:?Set PIP_AUDIT_BIN to an existing pip-audit executable}"

LOG_FILE=${VERIFY_LOG:-"${TMPDIR:-/tmp}/dabbarha-phase-2c1-verification-$(date +%Y%m%d-%H%M%S).log"}
mkdir -p "$(dirname -- "$LOG_FILE")"
: > "$LOG_FILE"
log() { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }
run_logged() { "$@" 2>&1 | tee -a "$LOG_FILE"; }

log "Phase 2c.1 verification log: $LOG_FILE"
log "Repository: $ROOT"
log "No package installation or upgrade will be performed."

finish() {
  result=$?
  trap - EXIT
  log ""
  log "=== Final working-tree and diff checks ==="
  if ! git -C "$ROOT" diff --check 2>&1 | tee -a "$LOG_FILE"; then result=1; fi
  if ! git -C "$ROOT" status --short --branch 2>&1 | tee -a "$LOG_FILE"; then result=1; fi
  if ! git -C "$ROOT" diff --stat 2>&1 | tee -a "$LOG_FILE"; then result=1; fi
  log "Verification exit status: $result"
  log "Complete log: $LOG_FILE"
  exit "$result"
}
trap finish EXIT

for executable in "$VERIFY_PYTHON" "$REDIS_SERVER_BINARY" "$POSTGRES_TEST_BIN/initdb" "$POSTGRES_TEST_BIN/postgres" "$PIP_AUDIT_BIN"; do
  if [[ ! -x "$executable" ]]; then
    log "Required executable is missing or not executable: $executable"
    exit 2
  fi
done

cd "$ROOT"
log ""
log "=== Runtime version preflight ==="
"$VERIFY_PYTHON" - "$ROOT/constraints-python312.txt" <<'PY' 2>&1 | tee -a "$LOG_FILE"
from importlib import metadata
from pathlib import Path
import platform
import sys

print(f"Interpreter: {sys.executable}")
print(f"Runtime: {platform.python_implementation()} {platform.python_version()} / {platform.system()} {platform.machine()}")
if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 12):
    raise SystemExit("Expected CPython 3.12; refusing to run tests.")

constraints = Path(sys.argv[1])
checked = 0
for raw in constraints.read_text(encoding="utf-8").splitlines():
    item = raw.strip()
    if not item or item.startswith("#") or "==" not in item:
        continue
    name, expected = item.split("==", 1)
    try:
        installed = metadata.version(name)
    except metadata.PackageNotFoundError:
        installed = "MISSING"
    print(f"Dependency: {name} expected={expected} installed={installed}")
    if installed != expected:
        raise SystemExit(f"Dependency pin mismatch for {name}; refusing to run tests.")
    checked += 1
if checked == 0:
    raise SystemExit("No exact dependency pins were found; refusing to run tests.")
print(f"Verified {checked} exact dependency pins.")
PY

pip_version=$("$VERIFY_PYTHON" -m pip --version)
log "Existing pip: $pip_version"
redis_version=$("$REDIS_SERVER_BINARY" --version)
log "Redis: $redis_version"
case "$redis_version" in
  *"v=7.4.11"*) ;;
  *) log "Expected Redis 7.4.11; refusing to run tests."; exit 2 ;;
esac
postgres_version=$("$POSTGRES_TEST_BIN/postgres" --version)
initdb_version=$("$POSTGRES_TEST_BIN/initdb" --version)
log "PostgreSQL server: $postgres_version"
log "PostgreSQL initdb: $initdb_version"
case "$postgres_version:$initdb_version" in
  *"18.6"*"18.6"*) ;;
  *) log "Expected PostgreSQL 18.6 server and initdb; refusing to run tests."; exit 2 ;;
esac
log "pip-audit: $("$PIP_AUDIT_BIN" --version)"

log ""
log "=== Isolated test configuration ==="
export APP_ENV=test
export RATE_LIMIT_BACKEND=memory
export DATABASE_URL=sqlite:///:memory:
export JWT_SECRET_KEY
JWT_SECRET_KEY=$("$VERIFY_PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export REQUIRE_REDIS_TESTS=1
export REDIS_SERVER_BINARY
export REQUIRE_POSTGRES_TESTS=1
export POSTGRES_TEST_BIN
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1
export PIP_CONFIG_FILE=/dev/null
export PIP_CACHE_DIR="${TMPDIR:-/tmp}/dabbarha-phase-2c1-pip-audit-cache/pip"
mkdir -p "$PIP_CACHE_DIR"

log "APP_ENV=test; application database is in-memory SQLite; JWT key is synthetic and will not be printed."
log "PostgreSQL and Redis fixtures must launch fresh disposable local instances; required-test flags are enabled."

SITE_PACKAGES=$("$VERIFY_PYTHON" -c 'import site; print(site.getsitepackages()[0])')

log ""
log "=== pip check ==="
run_logged "$VERIFY_PYTHON" -m pip check

log ""
log "=== pip-audit ==="
run_logged "$PIP_AUDIT_BIN" --path "$SITE_PACKAGES" --cache-dir "${TMPDIR:-/tmp}/dabbarha-phase-2c1-pip-audit-cache" --strict

log ""
log "=== Disposable SQLite and PostgreSQL migration upgrade/downgrade/re-upgrade tests ==="
run_logged "$VERIFY_PYTHON" -m pytest -vv -ra --tb=short -p no:cacheprovider \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db'

log ""
log "=== Complete backend suite (mandatory disposable Redis and PostgreSQL integration tests) ==="
run_logged "$VERIFY_PYTHON" -m pytest -vv -ra --tb=short -p no:cacheprovider

log ""
log "All required verification commands completed successfully."
