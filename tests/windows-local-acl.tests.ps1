# Native Windows regression suite. Uses only a fresh directory under TEMP.
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Native Windows required.' }
. (Join-Path $PSScriptRoot '..\scripts\windows-local-acl.ps1')
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$user = $sid.Value
foreach ($sddl in @(
    "O:SYD:P(A;;FA;;;$user)",
    "O:${user}D:(A;;FA;;;$user)",
    "O:${user}D:P(A;ID;FA;;;$user)",
    "O:${user}D:P(A;;FA;;;$user)(A;;FR;;;BU)",
    "O:${user}D:P(D;;FA;;;$user)",
    "O:${user}D:P(A;;FR;;;$user)",
    "O:${user}D:P(A;;FA;;;BU)"
)) {
    $bad = [System.Security.AccessControl.RawSecurityDescriptor]::new($sddl)
    if (Test-LocalConfigDescriptor $bad $sid) { throw 'Accepted an unsafe descriptor.' }
}
$root = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
[void][System.IO.Directory]::CreateDirectory($root)
try {
    $path = Join-Path $root '.env.local'
    Protect-LocalConfigFile $path
    if (-not (Test-LocalConfigDescriptor (Read-LocalConfigDescriptor $path) $sid)) { throw 'New file ACL incorrect.' }
    [System.IO.File]::WriteAllText($path, 'disposable fixture')
    $hash = (Get-FileHash -LiteralPath $path).Hash
    & {
        function Write-LocalConfigDescriptor { throw 'Already compliant file triggered an ACL write.' }
        Protect-LocalConfigFile $path
        Protect-LocalConfigFile $path
    }
    $acl = [System.Security.AccessControl.FileSecurity]::new()
    $acl.SetSecurityDescriptorSddlForm("D:P(A;;FA;;;$user)(A;;FR;;;BU)", [System.Security.AccessControl.AccessControlSections]::Access)
    $fixtureFile = [System.IO.FileInfo]::new($path)
    if ($PSVersionTable.PSEdition -eq 'Core') {
        [System.IO.FileSystemAclExtensions]::SetAccessControl($fixtureFile, $acl)
    } else {
        $fixtureFile.SetAccessControl($acl)
    }
    foreach ($mode in @('write failure', 'silent no-op')) {
        & {
            function Write-LocalConfigDescriptor {
                if ($mode -eq 'write failure') { throw [System.UnauthorizedAccessException]::new('PRIVATE_DIAGNOSTIC_CANARY') }
            }
            $message = ''
            try { Protect-LocalConfigFile $path } catch { $message = $_.Exception.Message }
            $expected = if ($mode -eq 'write failure') { 'apply private file permissions.*UnauthorizedAccessException' } else { 'verify persisted owner and DACL.*SecurityException' }
            if ($message -notmatch $expected -or $message -notmatch 'HRESULT=0x[0-9A-F]{8}, initially compliant=false' -or
                $message.Contains('PRIVATE_DIAGNOSTIC_CANARY') -or $message.Contains($path)) { throw 'Unsafe or missing failure diagnostic.' }
        }
    }
    Protect-LocalConfigFile $path
    if (-not (Test-LocalConfigDescriptor (Read-LocalConfigDescriptor $path) $sid)) { throw 'Repair failed.' }
    if ((Get-FileHash -LiteralPath $path).Hash -ne $hash) { throw 'Fixture contents changed.' }
    Write-Output 'PASS: native Windows file ACL regression checks'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
