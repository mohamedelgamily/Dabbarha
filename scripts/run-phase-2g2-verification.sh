#!/bin/bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
unset PYTHONPATH PYTHONHOME
: "${VERIFY_PYTHON:?Set VERIFY_PYTHON to the clean CPython 3.12 interpreter}"
: "${REDIS_SERVER_BINARY:?Set REDIS_SERVER_BINARY to the disposable Redis 7.4.11 binary}"
: "${POSTGRES_TEST_BIN:?Set POSTGRES_TEST_BIN to the disposable PostgreSQL 18.6 bin directory}"
: "${PIP_AUDIT_BIN:?Set PIP_AUDIT_BIN to an existing pip-audit executable}"
LOG_FILE=${VERIFY_LOG:-"${TMPDIR:-/tmp}/dabbarha-phase-2g2-verification-$(date +%Y%m%d-%H%M%S).log"}
mkdir -p "$(dirname -- "$LOG_FILE")"
: > "$LOG_FILE"
log() { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }
run_logged() { "$@" 2>&1 | tee -a "$LOG_FILE"; }

finish() {
  result=$?
  trap - EXIT
  log ""
  log "=== Final Git, whitespace, artifact and secret checks ==="
  if ! git -C "$ROOT" diff --check 2>&1 | tee -a "$LOG_FILE"; then result=1; fi
  if ! git -C "$ROOT" diff --cached --check 2>&1 | tee -a "$LOG_FILE"; then result=1; fi
  if ! git -C "$ROOT" diff --cached --quiet; then log "Unexpected staged changes found; Phase 2g.2 runner does not stage files."; result=1; fi
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    case "$path" in
      *.db|*.sqlite|*.sqlite3|*.log|*.pyc|*/__pycache__/*|.env|.env.*)
        case "$path" in .env.example|.env.*.example) ;; *) log "Unexpected generated/sensitive artifact path: $path"; result=1;; esac;;
    esac
    check_output=$(git -C "$ROOT" diff --no-index --check /dev/null "$ROOT/$path" 2>&1) || true
    if [[ -n "$check_output" ]]; then printf '%s\n' "$check_output" | tee -a "$LOG_FILE"; result=1; fi
  done < <(git -C "$ROOT" ls-files --others --exclude-standard)
  git -C "$ROOT" status --short --branch 2>&1 | tee -a "$LOG_FILE"
  git -C "$ROOT" diff --stat 2>&1 | tee -a "$LOG_FILE"
  if ! "$VERIFY_PYTHON" - "$ROOT" <<'PYSCAN' 2>&1 | tee -a "$LOG_FILE"; then result=1; fi
import re, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
tracked = subprocess.check_output(["git", "-C", str(root), "diff", "--name-only"], text=True).splitlines()
untracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"], text=True).splitlines()
patterns = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"), re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b"), re.compile(rb"\bsk-[A-Za-z0-9]{24,}\b"),
    re.compile(rb"(?i)(?:JWT_SECRET_KEY|RATE_LIMIT_HMAC_KEY|ADMIN_TOTP_ENCRYPTION_KEY|SESSION_RECEIPT_KEY|PUSH_TOKEN_ENCRYPTION_KEY)\s*=\s*['\"]?[A-Za-z0-9+/=_-]{32,}"),
]
bad = []
for relative in tracked + untracked:
    path = Path(relative)
    if path.name == ".env" or (path.name.startswith(".env.") and not path.name.endswith(".example")):
        bad.append(relative); continue
    try: data = (root / path).read_bytes()
    except OSError: bad.append(relative); continue
    if any(pattern.search(data) for pattern in patterns): bad.append(relative)
if bad:
    print("Potential secret, real env file, or unreadable changed path detected:", ", ".join(bad))
    raise SystemExit(1)
print("Changed-file secret scan passed; no real .env or ignored files were read.")
PYSCAN
  log "Verification exit status: $result"
  log "Complete log: $LOG_FILE"
  exit "$result"
}
trap finish EXIT

for executable in "$VERIFY_PYTHON" "$REDIS_SERVER_BINARY" "$POSTGRES_TEST_BIN/initdb" "$POSTGRES_TEST_BIN/postgres" "$PIP_AUDIT_BIN"; do
  [[ -x "$executable" ]] || { log "Required executable missing/not executable: $executable"; exit 2; }
done
cd "$ROOT"
log "Phase 2g.2 verification log: $LOG_FILE"
log "Repository: $ROOT"
log "No packages will be installed or upgraded."
"$VERIFY_PYTHON" - "$ROOT/constraints-python312.txt" "$ROOT/requirements-linux-py312.lock" <<'PYCHECK' 2>&1 | tee -a "$LOG_FILE"
from importlib import metadata
from pathlib import Path
import platform, re, sys
print(f"Interpreter: {sys.executable}")
print(f"Runtime: {platform.python_implementation()} {platform.python_version()} / {platform.system()} {platform.machine()}")
if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 12): raise SystemExit("Expected CPython 3.12")
if platform.system() != "Darwin" or platform.machine() not in {"arm64", "x86_64"}: raise SystemExit("Expected a supported macOS verification host")
count = 0
for raw in Path(sys.argv[1]).read_text().splitlines():
    item = raw.strip()
    if not item or item.startswith("#") or "==" not in item: continue
    name, expected = item.split("==", 1)
    try: installed = metadata.version(name)
    except metadata.PackageNotFoundError: installed = "MISSING"
    print(f"Dependency: {name} expected={expected} installed={installed}")
    if installed != expected: raise SystemExit(f"Dependency pin mismatch: {name}")
    count += 1
if count != 44: raise SystemExit(f"Expected 44 exact dependency pins, found {count}")
print(f"Verified all {count} exact dependency pins")
normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
locked = {}
lock_text = Path(sys.argv[2]).read_text()
for raw in lock_text.splitlines():
    item = raw.strip()
    if not item or item.startswith("#") or "==" not in item: continue
    name, version = item.split("==", 1)
    locked[normalize(name)] = version.rstrip().rstrip("\\").strip()
expected = {}
for raw in Path(sys.argv[1]).read_text().splitlines():
    item = raw.strip()
    if item and not item.startswith("#") and "==" in item:
        name, version = item.split("==", 1); expected[normalize(name)] = version
if locked != expected: raise SystemExit("Linux lock package/version set differs from exact constraints")
hash_lines = re.findall(r"--hash=sha256:[0-9a-f]{64}", lock_text)
if len(hash_lines) != len(expected): raise SystemExit(f"Expected one Linux wheel hash for each locked package, found {len(hash_lines)}")
print(f"Verified Linux CPython 3.12 lock: {len(locked)} matching pins and {len(hash_lines)} SHA-256 hashes; Linux runtime itself is not exercised on this Mac.")
PYCHECK
log "pip: $($VERIFY_PYTHON -m pip --version)"
redis_version=$($REDIS_SERVER_BINARY --version)
postgres_version=$($POSTGRES_TEST_BIN/postgres --version)
initdb_version=$($POSTGRES_TEST_BIN/initdb --version)
log "Redis: $redis_version"
log "PostgreSQL: $postgres_version"
log "PostgreSQL initdb: $initdb_version"
[[ "$redis_version" == *"v=7.4.11"* ]] || { log "Expected Redis 7.4.11"; exit 2; }
[[ "$postgres_version:$initdb_version" == *"18.6"*"18.6"* ]] || { log "Expected PostgreSQL 18.6"; exit 2; }
log "pip-audit: $($PIP_AUDIT_BIN --version)"

export APP_ENV=test RATE_LIMIT_BACKEND=memory
unset JWT_SECRET_KEY JWT_ALGORITHM RATE_LIMIT_HMAC_KEY RATE_LIMIT_REDIS_URL
unset SESSION_RECEIPT_KEY ADMIN_TOTP_ENCRYPTION_KEY ADMIN_TOTP_KEY_ID
unset PUSH_TOKEN_ENCRYPTION_KEY EXPO_PUSH_ACCESS_TOKEN DATABASE_URL
unset PGDATABASE PGHOST PGPORT PGUSER PGPASSWORD PGPASSFILE PGSERVICE PGSERVICEFILE PGOPTIONS PGDATA
unset PGSSLMODE PGSSLROOTCERT PGSSLCERT PGSSLKEY
export DATABASE_URL=sqlite:///:memory: ADMIN_API_ENABLED=false ADMIN_TOTP_KEY_ID=v1 ADMIN_STEPUP_TOKEN_MINUTES=5
JWT_SECRET_KEY=$($VERIFY_PYTHON -c 'import secrets; print(secrets.token_urlsafe(48))')
export JWT_SECRET_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export SESSION_AUTH_ENABLED=false SESSION_LEGACY_ISSUANCE=true SESSION_LEGACY_ACCEPTANCE=true
export NOTIFICATIONS_ENABLED=false NOTIFICATION_DELIVERY_ENABLED=false
export REQUIRE_REDIS_TESTS=1 REDIS_SERVER_BINARY REQUIRE_POSTGRES_TESTS=1 POSTGRES_TEST_BIN
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 PIP_CONFIG_FILE=/dev/null
PIP_AUDIT_CACHE_DIR="${TMPDIR:-/tmp}/dabbarha-phase-2g2-pip-audit-cache"; mkdir -p "$PIP_AUDIT_CACHE_DIR"; export PIP_AUDIT_CACHE_DIR
SITE_PACKAGES=$($VERIFY_PYTHON -c 'import site; print(site.getsitepackages()[0])')

log "=== Static deployment configuration checks ==="
"$VERIFY_PYTHON" - "$ROOT" <<'PYCONFIG' 2>&1 | tee -a "$LOG_FILE"
from configparser import ConfigParser
from pathlib import Path
import sys
root = Path(sys.argv[1])
api = ConfigParser(interpolation=None); api.read(root / "deploy/dabbarha-api.service.example")
worker = ConfigParser(interpolation=None); worker.read(root / "deploy/dabbarha-notifications.service.example")
for name, parser in (("API", api), ("worker", worker)):
    if not parser.has_section("Service"): raise SystemExit(f"{name} unit missing Service section")
    service = parser["Service"]
    for key in ("User", "Group", "EnvironmentFile", "ExecStart", "Restart", "NoNewPrivileges", "ProtectSystem", "ProtectHome"):
        if not service.get(key): raise SystemExit(f"{name} unit missing {key}")
    if service.get("NoNewPrivileges") != "true" or service.get("ProtectSystem") != "strict":
        raise SystemExit(f"{name} unit missing required hardening")
if api["Service"]["User"] == worker["Service"]["User"]: raise SystemExit("API and worker must have separate service users")
if api["Service"]["EnvironmentFile"] == worker["Service"]["EnvironmentFile"]: raise SystemExit("API and worker must have separate environment files")
if "--reload" in api["Service"]["ExecStart"] or "--no-access-log" not in api["Service"]["ExecStart"]:
    raise SystemExit("API command must disable reload and access logging")
if "--host 127.0.0.1" not in api["Service"]["ExecStart"] or "--forwarded-allow-ips 127.0.0.1" not in api["Service"]["ExecStart"]:
    raise SystemExit("VPS API example must bind/trust loopback only")
caddy = (root / "deploy/Caddyfile.example").read_text()
redis = (root / "deploy/redis.conf.example").read_text()
if "request_body" not in caddy or "max_size 65536" not in caddy or "header_up X-Forwarded-For" not in caddy:
    raise SystemExit("Caddy example missing body/forwarded-header controls")
if "port 0" not in redis or "unixsocket " not in redis or "unixsocketperm 770" not in redis:
    raise SystemExit("Redis example must disable TCP and use a restricted Unix socket")
env = {}
for line in (root / ".env.production.example").read_text().splitlines():
    line=line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    key, value=line.split("=",1); env[key.strip()]=value.strip().strip("\"'")
for key in ("JWT_SECRET_KEY", "RATE_LIMIT_HMAC_KEY", "SESSION_RECEIPT_KEY", "PUSH_TOKEN_ENCRYPTION_KEY", "EXPO_PUSH_ACCESS_TOKEN"):
    if env.get(key, "") != "": raise SystemExit(f"Production template secret must remain blank: {key}")
if env.get("APP_ENV") != "production" or env.get("API_DOCS_ENABLED") != "false":
    raise SystemExit("Production example must keep explicit production mode and docs disabled")
print("Static service, proxy, Redis and blank-secret-template checks passed")
PYCONFIG
bash -n scripts/run-phase-2g2-verification.sh
if command -v caddy >/dev/null 2>&1; then run_logged caddy validate --config deploy/Caddyfile.example --adapter caddyfile; else log "Caddy binary unavailable on this Mac; Caddy syntax receives static checks only."; fi
if command -v systemd-analyze >/dev/null 2>&1; then run_logged systemd-analyze verify deploy/dabbarha-api.service.example deploy/dabbarha-notifications.service.example; else log "systemd-analyze unavailable on this Mac; service units receive static INI/security checks only."; fi

log "=== pip check ==="
run_logged "$VERIFY_PYTHON" -m pip check
log "=== pip-audit ==="
run_logged "$PIP_AUDIT_BIN" --path "$SITE_PACKAGES" --cache-dir "$PIP_AUDIT_CACHE_DIR" --strict

log "=== Disposable PostgreSQL and Redis integration plus migration checks ==="
run_logged "$VERIFY_PYTHON" -m pytest -vv -ra --tb=short -p no:cacheprovider \
  tests/test_api_security.py::test_real_redis_expiry_and_reservation_release \
  tests/test_api_security.py::test_independent_worker_processes_share_one_quota \
  tests/test_api_security.py::test_actual_redis_runtime_startup_api_quota_and_private_socket \
  tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db \
  tests/test_admin_operations.py::test_worker_heartbeat_success_failure_and_staleness
for required_case in \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db[sqlite] PASSED' \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db[postgres] PASSED' \
  'tests/test_api_security.py::test_real_redis_expiry_and_reservation_release PASSED' \
  'tests/test_api_security.py::test_independent_worker_processes_share_one_quota PASSED' \
  'tests/test_api_security.py::test_actual_redis_runtime_startup_api_quota_and_private_socket PASSED' \
  'tests/test_admin_operations.py::test_worker_heartbeat_success_failure_and_staleness[sqlite] PASSED' \
  'tests/test_admin_operations.py::test_worker_heartbeat_success_failure_and_staleness[postgres] PASSED'; do
  grep -Fq "$required_case" "$LOG_FILE" || { log "Required integration case did not pass: $required_case"; exit 1; }
done

log "=== Complete backend suite; PostgreSQL and Redis integrations are mandatory ==="
run_logged "$VERIFY_PYTHON" -m pytest -vv -ra --tb=short -p no:cacheprovider
summary=$(grep -E '^=+ [0-9]+ passed' "$LOG_FILE" | tail -n 1 || true)
if [[ -z "$summary" || "$summary" == *skipped* || "$summary" == *deselected* || "$summary" == *failed* ]]; then
  log "Complete-suite summary missing or includes failures/skips: ${summary:-none}"; exit 1
fi
for required_case in \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db[sqlite] PASSED' \
  'tests/test_sessions.py::test_additive_migration_and_downgrade_only_disposable_db[postgres] PASSED' \
  'tests/test_api_security.py::test_real_redis_expiry_and_reservation_release PASSED' \
  'tests/test_api_security.py::test_independent_worker_processes_share_one_quota PASSED' \
  'tests/test_api_security.py::test_actual_redis_runtime_startup_api_quota_and_private_socket PASSED'; do
  grep -Fq "$required_case" "$LOG_FILE" || { log "Required full-suite integration did not pass: $required_case"; exit 1; }
done
log "All Phase 2g.2 checks passed against disposable local services only; no staging or production validation is implied."
