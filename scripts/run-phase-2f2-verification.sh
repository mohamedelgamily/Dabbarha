#!/bin/bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
unset PYTHONPATH PYTHONHOME
: "${VERIFY_PYTHON:?Set VERIFY_PYTHON to the clean CPython 3.12 verification interpreter}"
: "${REDIS_SERVER_BINARY:?Set REDIS_SERVER_BINARY to the disposable Redis binary}"
: "${POSTGRES_TEST_BIN:?Set POSTGRES_TEST_BIN to the disposable PostgreSQL bin directory}"
: "${PIP_AUDIT_BIN:?Set PIP_AUDIT_BIN to an existing pip-audit executable}"

LOG_FILE=${VERIFY_LOG:-"${TMPDIR:-/tmp}/dabbarha-phase-2f2-verification-$(date +%Y%m%d-%H%M%S).log"}
mkdir -p "$(dirname -- "$LOG_FILE")"
: > "$LOG_FILE"
log() { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }
run_logged() { "$@" 2>&1 | tee -a "$LOG_FILE"; }

finish() {
  result=$?
  trap - EXIT
  log ""
  log "=== Final diff and working-tree checks ==="
  if ! git -C "$ROOT" diff --check 2>&1 | tee -a "$LOG_FILE"; then result=1; fi
  while IFS= read -r untracked; do
    [[ -n "$untracked" ]] || continue
    check_output=$(git -C "$ROOT" diff --no-index --check /dev/null "$untracked" 2>&1) || true
    if [[ -n "$check_output" ]]; then printf '%s\n' "$check_output" | tee -a "$LOG_FILE"; result=1; fi
  done < <(git -C "$ROOT" ls-files --others --exclude-standard)
  git -C "$ROOT" status --short --branch 2>&1 | tee -a "$LOG_FILE"
  git -C "$ROOT" diff --stat 2>&1 | tee -a "$LOG_FILE"
  if ! "$VERIFY_PYTHON" - "$ROOT" <<'PY' 2>&1 | tee -a "$LOG_FILE"; then result=1; fi
import re, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
tracked = subprocess.check_output(["git", "-C", str(root), "diff", "--name-only"], text=True).splitlines()
untracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"], text=True).splitlines()
patterns = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9]{24,}\b"),
]
bad = []
for relative in tracked + untracked:
    path = Path(relative)
    if path.name == ".env" or path.name.startswith(".env.") and not path.name.endswith(".example"):
        bad.append(relative)
        continue
    try:
        data = (root / path).read_bytes()
    except OSError:
        bad.append(relative)
        continue
    if any(pattern.search(data) for pattern in patterns):
        bad.append(relative)
if bad:
    print("Potential secret or unreadable changed path detected:", ", ".join(bad))
    raise SystemExit(1)
print("Changed-file secret scan passed; real .env files and ignored files were not read.")
PY
  log "Verification exit status: $result"
  log "Complete log: $LOG_FILE"
  exit "$result"
}
trap finish EXIT

for executable in "$VERIFY_PYTHON" "$REDIS_SERVER_BINARY" "$POSTGRES_TEST_BIN/initdb" "$POSTGRES_TEST_BIN/postgres" "$PIP_AUDIT_BIN"; do
  [[ -x "$executable" ]] || { log "Required executable missing/not executable: $executable"; exit 2; }
done

cd "$ROOT"
log "Phase 2f.2 verification log: $LOG_FILE"
log "Repository: $ROOT"
log "No packages will be installed or upgraded."
"$VERIFY_PYTHON" - "$ROOT/constraints-python312.txt" <<'PY' 2>&1 | tee -a "$LOG_FILE"
from importlib import metadata
from pathlib import Path
import platform, sys
print(f"Interpreter: {sys.executable}")
print(f"Runtime: {platform.python_implementation()} {platform.python_version()} / {platform.system()} {platform.machine()}")
if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 12):
    raise SystemExit("Expected CPython 3.12")
if platform.system() != "Darwin" or platform.machine() not in {"arm64", "x86_64"}:
    raise SystemExit("Expected an approved macOS verification host")
checked = 0
for raw in Path(sys.argv[1]).read_text().splitlines():
    item = raw.strip()
    if not item or item.startswith("#") or "==" not in item: continue
    name, expected = item.split("==", 1)
    try: installed = metadata.version(name)
    except metadata.PackageNotFoundError: installed = "MISSING"
    print(f"Dependency: {name} expected={expected} installed={installed}")
    if installed != expected: raise SystemExit(f"Dependency pin mismatch: {name}")
    checked += 1
if not checked: raise SystemExit("No exact pins found")
print(f"Verified {checked} exact dependency pins")
PY
log "pip: $("$VERIFY_PYTHON" -m pip --version)"
redis_version=$("$REDIS_SERVER_BINARY" --version)
postgres_version=$("$POSTGRES_TEST_BIN/postgres" --version)
initdb_version=$("$POSTGRES_TEST_BIN/initdb" --version)
log "Redis: $redis_version"
log "PostgreSQL: $postgres_version"
log "PostgreSQL initdb: $initdb_version"
[[ "$redis_version" == *"v=7.4.11"* ]] || { log "Expected Redis 7.4.11"; exit 2; }
[[ "$postgres_version:$initdb_version" == *"18.6"*"18.6"* ]] || { log "Expected PostgreSQL 18.6"; exit 2; }
log "pip-audit: $("$PIP_AUDIT_BIN" --version)"

export APP_ENV=test RATE_LIMIT_BACKEND=memory
# Do not inherit any credential or service configuration from the invoking shell.
unset JWT_SECRET_KEY JWT_ALGORITHM RATE_LIMIT_HMAC_KEY RATE_LIMIT_REDIS_URL
unset SESSION_RECEIPT_KEY ADMIN_TOTP_ENCRYPTION_KEY ADMIN_TOTP_KEY_ID
unset PUSH_TOKEN_ENCRYPTION_KEY EXPO_PUSH_ACCESS_TOKEN DATABASE_URL
# Isolate the disposable fixture from local libpq service and connection settings.
unset PGDATABASE PGHOST PGPORT PGUSER PGPASSWORD PGPASSFILE PGSERVICE PGSERVICEFILE PGOPTIONS PGDATA
unset PGSSLMODE PGSSLROOTCERT PGSSLCERT PGSSLKEY
unset ADMIN_STEPUP_TOKEN_MINUTES
export DATABASE_URL=sqlite:///:memory: ADMIN_API_ENABLED=false ADMIN_TOTP_KEY_ID=v1 ADMIN_STEPUP_TOKEN_MINUTES=5
export JWT_SECRET_KEY
JWT_SECRET_KEY=$("$VERIFY_PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export SESSION_AUTH_ENABLED=false SESSION_LEGACY_ISSUANCE=true SESSION_LEGACY_ACCEPTANCE=true
export ADMIN_API_ENABLED=false NOTIFICATIONS_ENABLED=false NOTIFICATION_DELIVERY_ENABLED=false
export REQUIRE_REDIS_TESTS=1 REDIS_SERVER_BINARY REQUIRE_POSTGRES_TESTS=1 POSTGRES_TEST_BIN
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 PIP_CONFIG_FILE=/dev/null
PIP_CACHE_DIR="${TMPDIR:-/tmp}/dabbarha-phase-2f2-pip-cache"
mkdir -p "$PIP_CACHE_DIR"
export PIP_CACHE_DIR
PIP_AUDIT_CACHE_DIR="${TMPDIR:-/tmp}/dabbarha-phase-2f2-pip-audit-cache"
mkdir -p "$PIP_AUDIT_CACHE_DIR"
SITE_PACKAGES=$("$VERIFY_PYTHON" -c 'import site; print(site.getsitepackages()[0])')

log "=== pip check ==="
run_logged "$VERIFY_PYTHON" -m pip check
log "=== pip-audit ==="
run_logged "$PIP_AUDIT_BIN" --path "$SITE_PACKAGES" --cache-dir "$PIP_AUDIT_CACHE_DIR" --strict
log "=== Targeted admin operations and additive migration tests (SQLite and PostgreSQL required) ==="
run_logged "$VERIFY_PYTHON" -m pytest -vv -ra --tb=short -p no:cacheprovider \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db' \
  'tests/test_sessions.py::test_admin_totp_step_up_is_session_bound_audited_and_replay_safe' \
  'tests/test_sessions.py::test_admin_rejects_legacy_access_tokens' \
  'tests/test_sessions.py::test_admin_totp_concurrent_replay_only_one_step_up' \
  'tests/test_api_security.py::test_admin_totp_step_up_uses_shared_account_ip_attempt_limits' \
  tests/test_admin_security.py tests/test_admin_operations.py \
  tests/test_v1_release.py::test_application_has_no_retired_imports_or_provider_requirements
log "=== Complete backend suite; Redis/PostgreSQL are mandatory and skips fail verification ==="
run_logged "$VERIFY_PYTHON" -m pytest -vv -ra --tb=short -p no:cacheprovider
summary=$(grep -E '^=+ [0-9]+ passed' "$LOG_FILE" | tail -n 1 || true)
if [[ -z "$summary" || "$summary" == *skipped* || "$summary" == *deselected* || "$summary" == *failed* ]]; then
  log "The complete-suite summary is missing or contains failures/skips: ${summary:-none}"
  exit 1
fi
for required_case in \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db[sqlite] PASSED' \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db[postgres] PASSED' \
  'tests/test_sessions.py::test_admin_totp_step_up_is_session_bound_audited_and_replay_safe[sqlite] PASSED' \
  'tests/test_sessions.py::test_admin_totp_step_up_is_session_bound_audited_and_replay_safe[postgres] PASSED' \
  'tests/test_sessions.py::test_admin_totp_concurrent_replay_only_one_step_up[postgres] PASSED' \
  'tests/test_admin_operations.py::test_operational_admin_metrics_are_accurate_and_do_not_expose_finances[postgres] PASSED' \
  'tests/test_admin_operations.py::test_worker_heartbeat_success_failure_and_staleness[postgres] PASSED' \
  'tests/test_api_security.py::test_real_redis_expiry_and_reservation_release PASSED' \
  'tests/test_api_security.py::test_independent_worker_processes_share_one_quota PASSED' \
  'tests/test_api_security.py::test_actual_redis_runtime_startup_api_quota_and_private_socket PASSED'; do
  grep -Fq "$required_case" "$LOG_FILE" || { log "Required integration test did not pass: $required_case"; exit 1; }
done
log "All Phase 2f.2 dependency, migration, Redis, PostgreSQL and backend checks passed."
