[CmdletBinding()]
param(
    [switch]$ListenOnLan,
    [switch]$ApplyMigrations,
    [ValidateRange(1024, 65535)][int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$config = Join-Path $repoRoot '.env.local'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Run .\scripts\setup-local-windows.ps1 first; the repository-local Python environment is missing.'
}
$tracked = & git -C $repoRoot ls-files -- .env.local
if ($LASTEXITCODE -ne 0 -or $tracked) { throw 'Refusing to use a tracked .env.local.' }
$ignored = & git -C $repoRoot check-ignore --no-index --quiet .env.local
if ($LASTEXITCODE -ne 0) { throw '.env.local is not ignored by Git. Refusing to start.' }
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw 'Run .\scripts\setup-local-windows.ps1 first to create the ignored local configuration.'
}

if ($ApplyMigrations) {
    & $python -I (Join-Path $repoRoot 'scripts\local_windows_config.py') apply-migrations --root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'Local migration did not complete. The API was not started.' }
}

$hostAddress = '127.0.0.1'
if ($ListenOnLan) {
    $hostAddress = '0.0.0.0'
    Write-Host 'LAN mode is enabled for this run. Use only a trusted private Wi-Fi network.'
    Write-Host 'No Windows Firewall rule was created. If required, allow TCP only from LocalSubnet on the Private profile.'
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.AddressState -eq 'Preferred' } |
        ForEach-Object { Write-Host ("Phone URL candidate: http://{0}:{1}" -f $_.IPAddress, $Port) }
    Write-Host 'Use the current reachable Wi-Fi address in Expo EXPO_PUBLIC_API_URL; do not save an IP in source code.'
} else {
    Write-Host 'Listening on loopback only. Use -ListenOnLan only when testing from a physical phone.'
}

& $python -I (Join-Path $repoRoot 'scripts\local_windows_config.py') serve --root $repoRoot --host $hostAddress --port $Port
if ($LASTEXITCODE -ne 0) { throw 'The local API stopped or could not start.' }
