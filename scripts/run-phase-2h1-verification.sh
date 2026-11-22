#!/bin/bash
set -euo pipefail
umask 077

ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
WORK="$HOME/Documents/Codex/2026-10-21/files-pasted-by-the-user-you/work"
LOG=$(mktemp "${TMPDIR:-/tmp}/dabbarha-phase-2h1-verification.XXXXXXXX")
printf 'Phase 2h.1 log: %s\n' "$LOG"

# Inherit host paths and locale only. Test fixtures start their own services.
exec env -i HOME="$HOME" PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
  TMPDIR="${TMPDIR:-/tmp}" LANG=en_US.UTF-8 PYTHONNOUSERSITE=1 \
  VERIFY_PYTHON="${VERIFY_PYTHON:-$WORK/batch6/implementation/secure-venv/bin/python}" \
  REDIS_SERVER_BINARY="${REDIS_SERVER_BINARY:-$WORK/batch5/redis-7.4.11/src/redis-server}" \
  POSTGRES_TEST_BIN="${POSTGRES_TEST_BIN:-$WORK/batch6/implementation/pg-runtime/bin}" \
  PIP_AUDIT_BIN="${PIP_AUDIT_BIN:-$WORK/batch3/audit-venv/bin/pip-audit}" \
  VERIFY_LOG="$LOG" /bin/bash "$ROOT/scripts/run-phase-2g3-verification.sh" --phase-2h1
