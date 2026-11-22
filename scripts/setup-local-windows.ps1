[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$gitRoot = (& git -C $repoRoot rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or (Resolve-Path $gitRoot).Path -ne $repoRoot) {
    throw 'Run this script from a complete Dabbarha backend Git checkout.'
}

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw @'
The repository-local Python environment is missing. Install CPython 3.12, then run:
  py -3.12 -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Rerun this setup script after installation. It does not install packages automatically.
'@
}

& $python -I -c "import sys; assert sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12), 'Use CPython 3.12'; import fastapi, uvicorn, sqlalchemy, alembic, jwt, dotenv, redis"
if ($LASTEXITCODE -ne 0) {
    throw 'The local venv must use CPython 3.12 and contain the backend requirements. Repair only .venv with requirements.txt, then rerun setup.'
}
& $python -I -m pip check
if ($LASTEXITCODE -ne 0) { throw 'The local venv has inconsistent dependencies. Repair .venv before continuing.' }

$tracked = & git -C $repoRoot ls-files -- .env.local
if ($LASTEXITCODE -ne 0 -or $tracked) { throw 'Refusing to use a tracked .env.local.' }
$ignored = & git -C $repoRoot check-ignore --no-index --quiet .env.local
if ($LASTEXITCODE -ne 0) { throw '.env.local is not ignored by Git. Refusing to create local secrets.' }
& $python -I (Join-Path $repoRoot 'scripts\local_windows_config.py') check-config-path --root $repoRoot
if ($LASTEXITCODE -ne 0) { throw 'Refusing to change permissions on an unsafe configuration path.' }
$config = Join-Path $repoRoot '.env.local'
try {
    if (Test-Path -LiteralPath $config) {
        $configItem = Get-Item -Force -LiteralPath $config
        if (($configItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Symbolic links are not accepted.'
        }
    } else {
        [void](New-Item -ItemType File -Path $config)
    }
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = Get-Acl -LiteralPath $config
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($existingRule in @($acl.Access)) { $acl.RemoveAccessRuleSpecific($existingRule) }
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    [void]$acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $config -AclObject $acl
} catch {
    throw 'Could not restrict .env.local access to the current Windows account. Review its file permissions before starting the API.'
}

& $python -I (Join-Path $repoRoot 'scripts\local_windows_config.py') ensure --root $repoRoot
if ($LASTEXITCODE -ne 0) { throw 'Local configuration was not created or validated. No secret values were displayed.' }
& $python -I (Join-Path $repoRoot 'scripts\local_windows_config.py') validate --root $repoRoot
if ($LASTEXITCODE -ne 0) { throw 'The local configuration did not pass validation.' }
& $python -I (Join-Path $repoRoot 'scripts\local_windows_config.py') redis-check --root $repoRoot
if ($LASTEXITCODE -ne 0) { throw 'The configured Redis prerequisite is unavailable.' }
$migrationOutput = & $python -I (Join-Path $repoRoot 'scripts\local_windows_config.py') migration-status --root $repoRoot
$migrationCode = $LASTEXITCODE
$migrationOutput | Write-Host
if ($migrationCode -eq 3) {
    Write-Host 'Migration status is pending. Setup did not change the database; use the startup script only after inspecting and backing up local data.'
} elseif ($migrationCode -ne 0) {
    throw 'The local database prerequisite could not be inspected safely.'
}
Write-Host 'Setup is ready. Local secrets are stored in ignored .env.local and were not displayed.'
