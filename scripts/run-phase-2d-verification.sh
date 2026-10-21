#!/bin/bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
: "${VERIFY_PYTHON:?Set VERIFY_PYTHON to the existing clean CPython 3.12 verification interpreter}"
: "${REDIS_SERVER_BINARY:?Set REDIS_SERVER_BINARY to the disposable Redis 7.4.11 binary}"
: "${POSTGRES_TEST_BIN:?Set POSTGRES_TEST_BIN to the disposable PostgreSQL 18.6 bin directory}"
: "${PIP_AUDIT_BIN:?Set PIP_AUDIT_BIN to an existing pip-audit executable}"

LOG_FILE=${VERIFY_LOG:-"${TMPDIR:-/tmp}/dabbarha-phase-2d-verification-$(date +%Y%m%d-%H%M%S).log"}
mkdir -p "$(dirname -- "$LOG_FILE")"
: > "$LOG_FILE"
log() { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }
run_logged() { "$@" 2>&1 | tee -a "$LOG_FILE"; }

log "Phase 2d verification log: $LOG_FILE"
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
log "=== Runtime and exact dependency pin preflight ==="
"$VERIFY_PYTHON" - "$ROOT/constraints-python312.txt" <<'PY' 2>&1 | tee -a "$LOG_FILE"
from importlib import metadata
from pathlib import Path
import platform
import sys

print(f"Interpreter: {sys.executable}")
print(f"Runtime: {platform.python_implementation()} {platform.python_version()} / {platform.system()} {platform.machine()}")
if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 12):
    raise SystemExit("Expected CPython 3.12; refusing to run tests.")
if platform.system() != "Darwin" or platform.machine() not in {"arm64", "x86_64"}:
    raise SystemExit("Expected the approved macOS verification host; refusing to run tests.")
checked = 0
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
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

log "Existing pip: $("$VERIFY_PYTHON" -m pip --version)"
redis_version=$("$REDIS_SERVER_BINARY" --version)
postgres_version=$("$POSTGRES_TEST_BIN/postgres" --version)
initdb_version=$("$POSTGRES_TEST_BIN/initdb" --version)
log "Redis: $redis_version"
log "PostgreSQL: $postgres_version"
log "PostgreSQL initdb: $initdb_version"
[[ "$redis_version" == *"v=7.4.11"* ]] || { log "Expected Redis 7.4.11."; exit 2; }
[[ "$postgres_version:$initdb_version" == *"18.6"*"18.6"* ]] || { log "Expected PostgreSQL 18.6."; exit 2; }
log "pip-audit: $("$PIP_AUDIT_BIN" --version)"

export APP_ENV=test RATE_LIMIT_BACKEND=memory DATABASE_URL=sqlite:///:memory:
export JWT_SECRET_KEY
JWT_SECRET_KEY=$("$VERIFY_PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export SESSION_AUTH_ENABLED=false NOTIFICATIONS_ENABLED=false NOTIFICATION_DELIVERY_ENABLED=false
export REQUIRE_REDIS_TESTS=1 REDIS_SERVER_BINARY
export REQUIRE_POSTGRES_TESTS=1 POSTGRES_TEST_BIN
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 PIP_CONFIG_FILE=/dev/null
export PIP_CACHE_DIR="${TMPDIR:-/tmp}/dabbarha-phase-2d-pip-audit-cache/pip"
mkdir -p "$PIP_CACHE_DIR"
SITE_PACKAGES=$("$VERIFY_PYTHON" -c 'import site; print(site.getsitepackages()[0])')

log ""
log "=== pip check ==="
run_logged "$VERIFY_PYTHON" -m pip check
log ""
log "=== pip-audit ==="
run_logged "$PIP_AUDIT_BIN" --path "$SITE_PACKAGES" --cache-dir "${TMPDIR:-/tmp}/dabbarha-phase-2d-pip-audit-cache" --strict
log ""
log "=== Disposable SQLite/PostgreSQL migration tests and concurrent worker claim test ==="
run_logged "$VERIFY_PYTHON" -m pytest -vv -ra --tb=short -p no:cacheprovider \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db' \
  'tests/test_notifications.py::test_concurrent_workers_atomically_claim_one_delivery'
log ""
log "=== Complete suite (Redis/PostgreSQL integration tests are mandatory) ==="
run_logged "$VERIFY_PYTHON" -m pytest -vv -ra --tb=short -p no:cacheprovider
log ""
log "All required Phase 2d verification commands completed successfully."
