# Dependency security and reproducible installation — Phase 2b.3

## Supported target and verification limits

Planned deployment: Ubuntu Server 24.04 LTS, x86_64, a currently supported
security-patched CPython 3.12, FastAPI/Uvicorn and future PostgreSQL. This phase
adds no PostgreSQL driver, connection configuration or schema migration. That
production-database integration remains a separate approved phase.

Local verification used a fresh isolated environment on macOS Intel with the
existing CPython 3.12.0 interpreter and in-memory SQLite. The existing repository
`.venv` was preserved, including its older packages. No real `.env` file, signing
key, provider key, database or frontend file was changed. Production must use a
current security-patched interpreter; these package pins do not patch Python.

All 40 resolved application/test distributions have CPython 3.12-compatible Linux
x86_64 wheels. The complete target dependency graph was checked with Linux markers
and the existing Uvicorn standard/pwdlib Argon2 extras. Each chosen artifact matched
its published PyPI SHA-256. The Linux lock was replayed offline using only those
wheels and mandatory hashes. This verifies dependency resolution, metadata, wheel
availability and artifact integrity, **not execution on Ubuntu or PostgreSQL**.
No local Docker/Podman runtime was available for a Linux execution test. Run the
full suite on the target Linux host/CI before deployment.

## Files and exact installation

- `requirements.txt`: existing direct requirement set, security-fixed PyJWT floor,
  and automatic inclusion of `constraints-python312.txt`.
- `constraints-python312.txt`: exact versions for the complete clean Python 3.12
  dependency graph. These also apply to local macOS installation.
- `requirements-linux-py312.lock`: exact Linux wheel artifact hashes. This is a
  target-specific lock, not a macOS/Windows/ARM lock. It includes the existing
  pytest/httpx test requirements; this phase does not split runtime and test sets.

Use a **new** environment. Do not install over or manually purge packages from the
preserved `.venv`. Example commands use placeholder environment paths:

```sh
python3.12 -m venv /absolute/path/to/new-venv
/absolute/path/to/new-venv/bin/python -m pip install 'pip==26.2.2'
```

On Ubuntu 24.04 x86_64 / CPython 3.12:

```sh
/absolute/path/to/new-venv/bin/python -m pip install --only-binary=:all: --require-hashes -r requirements-linux-py312.lock
```

For local macOS verification, from the backend root:

```sh
/absolute/path/to/new-venv/bin/python -m pip install -r requirements.txt
```

Local version constraints do not pin binary build toolchains. In the verified Intel
macOS environment, argon2-cffi-bindings 26.1.0 built from its published source
release. The production Linux lock uses its compatible abi3 wheel instead and
prohibits source builds. Do not apply this Linux hash lock to macOS.

Validate a new environment before selecting it for use:

```sh
/absolute/path/to/new-venv/bin/python -m pip check
PYTHONDONTWRITEBYTECODE=1 /absolute/path/to/new-venv/bin/python -m pytest -q -p no:cacheprovider
```

Normal app startup still needs the explicit JWT/environment configuration from
`configuration.md`. Never print credentials or rotate a deployment key as part
of dependency installation. These commands are installation instructions, not
authorization to deploy, replace the active environment or change production data.

## Changes selected

| Distribution | Previous environment | Verified replacement | Reason |
|---|---|---|---|
| PyJWT | 2.13.0 | 2.15.1 | Compatible 2.x security fixes; nested-header exception regression |
| certifi | 2026.7.22 | 2026.10.19 | Updated trust bundle removing compromised emSign roots |
| Mako | 1.4.1 | 1.4.3 | Compatible 1.4 patch line containing traversal fix |
| urllib3 | 2.7.0 | Absent | Not required after retired provider stack is omitted from clean rebuild |
| pip (environment bootstrap only) | 26.2.1 | 26.2.2 | Pin the tool used to resolve/replay installations |

No other existing application/test distribution version changed. FastAPI 0.141.1,
SQLAlchemy 2.0.52, Alembic 1.19.1, Uvicorn 0.52.4, Pydantic 2.13.4 and pwdlib 0.3.1
were retained. No major dependency migration was selected. Pip-audit 2.10.1 ran
in a separate tool environment so its requests/urllib3 dependencies did not enter
the application environment.

The clean rebuild omits these 11 old distributions without uninstalling anything
from the original environment: charset-normalizer, cryptography, distro,
google-auth, google-genai, groq, pyasn1, pyasn1-modules, requests, sniffio, urllib3.
No chatbot dependency was restored to requirements, constraints or the lock.

## Verification and advisory results

- Fresh-environment full suite: **307 passed, 1 existing Starlette warning**.
- New deeply nested JWT-header tests failed against old PyJWT with RecursionError;
  they pass with 2.15.1 as InvalidTokenError/HTTP 401. Invalid signatures and ordinary
  malformed tokens remain rejected. No application exception workaround was added.
- A synthetic HS256 token and Argon2id hash produced under the original environment
  were accepted under the updated environment with the same synthetic key/password.
  No real credential or persistent data was used.
- OSV queries of all installed distributions: 52 packages / 19 distinct advisories
  before, 41 packages including pip / zero advisory hits after.
- Pip-audit 2.10.1 using OSV: before exit 1 with 38 GHSA/PYSEC records representing
  the same 19 issues; after exit 0, 41 packages, no skips, zero advisory entries.
- `pip check`: no broken requirements. Root requirements/constraints resolve to
  exactly the tested package versions. Linux hash-lock offline replay succeeds.

The advisory scans used public package names/versions only. A zero-hit result is
limited to the queried databases and audit date; it is not a proof of safety or
production readiness. Original `.venv` remains unchanged and still contains the
old vulnerable distributions. Use the validated clean build for future deployment.

## Refreshing pins safely

Keep existing pins while investigating a security update, then change only the
approved candidate versions in a clean environment. Resolve from the direct
requirements, inspect every added/removed/changed distribution, reject unexpected
major upgrades or retired provider packages, and run the full suite/security scan.
Update exact version constraints and, for production, download the complete
CPython 3.12 Linux x86_64 wheel closure using Ubuntu's compatible manylinux tags.
Verify hashes against authoritative package metadata, regenerate the target lock,
and replay it offline with `--only-binary=:all: --require-hashes` before approval.
Never update a requirements floor without refreshing and verifying its exact pins.

A PostgreSQL driver, Python minor change, another OS/architecture, package extras
change or runtime/test dependency split requires a new dependency resolution and
appropriate integration tests. None was silently inferred in this phase.

## Phase 2b.5 addition

The approved shared limiter adds **redis 8.1.0** (`redis>=8.1,<9.0`), without extras.
No existing dependency was upgraded or removed. A new isolated environment rebuilt
all dependencies from the root requirements and pins; the original `.venv` and
Phase 2b.3 verification environment were preserved. The constraints and Linux
CPython 3.12 hash lock now contain 41 application/test distributions. The Linux
marker/extra closure, published PyPI wheel hashes and offline hash-lock replay
were verified again. The historical Phase 2b.3 counts above describe that phase.

A disposable **Redis server 7.4.11**, built from the official archive with its
published SHA-256 verified, runs integration tests with TCP disabled on a private
Unix socket. It is a test runtime outside the repository, not a Python dependency,
a production installation or a choice to change an existing deployed service.
Use a supported, patched Redis server matching the reviewed client compatibility;
do not assume an arbitrary distribution package matches the tested baseline.
The full Python environment scan is recorded in the Phase 2b.5 verification report.
