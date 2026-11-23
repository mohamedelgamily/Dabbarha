# Inspect every DACL entry directly, including ACE types omitted by managed rule views.
function Test-LocalConfigDescriptor($Descriptor, $Sid) {
    $dacl = $Descriptor.DiscretionaryAcl
    $flags = [System.Security.AccessControl.ControlFlags]
    if (-not $Sid.Equals($Descriptor.Owner) -or
        -not $Descriptor.ControlFlags.HasFlag($flags::DiscretionaryAclPresent) -or
        -not $Descriptor.ControlFlags.HasFlag($flags::DiscretionaryAclProtected) -or
        $null -eq $dacl -or $dacl.Count -ne 1) { return $false }
    $ace = $dacl[0]
    return ($ace -is [System.Security.AccessControl.CommonAce] -and
        -not $ace.IsCallback -and $ace.OpaqueLength -eq 0 -and
        $ace.AceType -eq [System.Security.AccessControl.AceType]::AccessAllowed -and
        $ace.AceFlags -eq [System.Security.AccessControl.AceFlags]::None -and
        $ace.AccessMask -eq [int][System.Security.AccessControl.FileSystemRights]::FullControl -and
        $Sid.Equals($ace.SecurityIdentifier))
}

function Read-LocalConfigDescriptor($Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($item -isnot [System.IO.FileInfo] -or $item.Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint)) {
        throw 'Expected an ordinary file.'
    }
    $acl = Get-Acl -LiteralPath $Path -ErrorAction Stop
    return [System.Security.AccessControl.RawSecurityDescriptor]::new($acl.GetSecurityDescriptorBinaryForm(), 0)
}

function Write-LocalConfigDescriptor($Path, $Sid, $ChangeOwner) {
    # Persist only the changed sections. Avoid requesting owner/group writes for a DACL repair.
    $acl = [System.Security.AccessControl.FileSecurity]::new()
    $acl.SetSecurityDescriptorSddlForm("D:P(A;;FA;;;$($Sid.Value))", [System.Security.AccessControl.AccessControlSections]::Access)
    if ($ChangeOwner) { $acl.SetOwner($Sid) }
    $file = [System.IO.FileInfo]::new($Path)
    if ($PSVersionTable.PSEdition -eq 'Core') {
        [System.IO.FileSystemAclExtensions]::SetAccessControl($file, $acl)
    } else {
        $file.SetAccessControl($acl)
    }
}

function Protect-LocalConfigFile($Path) {
    $initial = 'unknown'
    $operation = 'identify current Windows account'
    try {
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
        try { $sid = $identity.User } finally { $identity.Dispose() }
        $operation = 'locate or exclusively create empty configuration file'
        if (-not (Test-Path -LiteralPath $Path -ErrorAction Stop)) {
            [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew).Dispose()
        }
        $operation = 'read initial owner and DACL'
        $descriptor = Read-LocalConfigDescriptor $Path
        if (Test-LocalConfigDescriptor $descriptor $sid) { return }
        $initial = 'false'
        $operation = 'apply private file permissions'
        Write-LocalConfigDescriptor $Path $sid (-not $sid.Equals($descriptor.Owner))
        $operation = 'verify persisted owner and DACL'
        if (-not (Test-LocalConfigDescriptor (Read-LocalConfigDescriptor $Path) $sid)) {
            throw [System.Security.SecurityException]::new('Permission policy mismatch.')
        }
    } catch {
        $cause = $_.Exception.GetBaseException()
        $code = 'HRESULT=0x{0:X8}' -f $cause.HResult
        if ($cause -is [System.ComponentModel.Win32Exception]) { $code += ", Win32=$($cause.NativeErrorCode)" }
        throw "Local permission check failed during '$operation'. $($cause.GetType().FullName), $code, initially compliant=$initial. Setup stopped before configuring secrets."
    }
}
