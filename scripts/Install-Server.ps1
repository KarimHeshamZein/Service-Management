[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ServiceManagement',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$ServiceName = 'ServiceManagementSystem',
    [Parameter(Mandatory = $true)]
    [string]$WinSwPath,
    [string]$PythonExecutable = 'python.exe',
    [ValidateRange(1, 65535)]
    [int]$Port = 8993,
    [string]$DatabaseHost = '',
    [ValidateRange(0, 65535)]
    [int]$DatabasePort = 0,
    [string]$DatabaseName = '',
    [string]$DatabaseUsername = '',
    [Security.SecureString]$DatabasePassword
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Read-DotEnvValue {
    param([string]$Path, [string]$Name)
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^\s*$([Regex]::Escape($Name))\s*=" } |
        Select-Object -Last 1
    if (-not $line) { return $null }
    $value = ($line -split '=', 2)[1].Trim()
    if (
        $value.Length -ge 2 -and
        (($value.StartsWith('"') -and $value.EndsWith('"')) -or
         ($value.StartsWith("'") -and $value.EndsWith("'")))
    ) {
        return $value.Substring(1, $value.Length - 2)
    }
    return $value
}

function Resolve-DatabaseParts {
    param([string]$DatabaseUrl)
    $normalized = $DatabaseUrl -replace '^postgresql(\+[^:]+)?://', 'postgresql://'
    try {
        $uri = [Uri]$normalized
    } catch {
        throw 'DATABASE_URL is not a valid PostgreSQL URL.'
    }
    if ($uri.Scheme -ne 'postgresql' -or -not $uri.Host) {
        throw 'DATABASE_URL must use PostgreSQL and include a host.'
    }
    $credentials = $uri.UserInfo -split ':', 2
    if (-not $credentials[0]) {
        throw 'DATABASE_URL must include a PostgreSQL username.'
    }
    $databaseName = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    if (-not $databaseName) {
        throw 'DATABASE_URL must include a database name.'
    }
    return [ordered]@{
        Host = $uri.Host
        Port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
        Username = [Uri]::UnescapeDataString($credentials[0])
        Password = if ($credentials.Count -gt 1) {
            [Uri]::UnescapeDataString($credentials[1])
        } else { '' }
        Database = $databaseName
    }
}

function ConvertFrom-SecureValue {
    param([Security.SecureString]$SecureValue)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Test-PortableExecutable {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ([IO.Path]::GetExtension($Path) -ine '.exe') { return $false }
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $reader = New-Object IO.BinaryReader($stream)
    try {
        if ($stream.Length -lt 64) { return $false }
        if ($reader.ReadUInt16() -ne 0x5A4D) { return $false }
        $stream.Position = 0x3C
        $peOffset = $reader.ReadInt32()
        if ($peOffset -lt 0 -or ($peOffset + 4) -gt $stream.Length) { return $false }
        $stream.Position = $peOffset
        return $reader.ReadUInt32() -eq 0x00004550
    } finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Find-PsqlExecutable {
    $command = Get-Command 'psql.exe' -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $postgresRoot = Join-Path $env:ProgramFiles 'PostgreSQL'
    if (Test-Path -LiteralPath $postgresRoot -PathType Container) {
        $candidate = Get-ChildItem -LiteralPath $postgresRoot -Directory |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'bin\psql.exe' } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if ($candidate) { return $candidate }
    }
    throw (
        'psql.exe was not found. Install the PostgreSQL client tools or add its bin ' +
        'directory to PATH, then run the installer again.'
    )
}

function Test-PostgreSqlConnection {
    param([string]$PsqlExecutable, [Collections.IDictionary]$Database)
    $hadPassword = Test-Path -LiteralPath 'Env:PGPASSWORD'
    $hadConnectTimeout = Test-Path -LiteralPath 'Env:PGCONNECT_TIMEOUT'
    $hadHistory = Test-Path -LiteralPath 'Env:PSQL_HISTORY'
    $oldPassword = $env:PGPASSWORD
    $oldConnectTimeout = $env:PGCONNECT_TIMEOUT
    $oldHistory = $env:PSQL_HISTORY
    try {
        $env:PGPASSWORD = $Database.Password
        $env:PGCONNECT_TIMEOUT = '10'
        $env:PSQL_HISTORY = 'NUL'
        & $PsqlExecutable --no-password --no-psqlrc --quiet --tuples-only `
            "--host=$($Database.Host)" "--port=$($Database.Port)" `
            "--username=$($Database.Username)" "--dbname=$($Database.Database)" `
            --command 'SELECT 1;' 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw (
                'PostgreSQL could not be reached with the supplied database details. ' +
                'Check the server, port, database, username and password, then try again.'
            )
        }
    } finally {
        if ($hadPassword) {
            $env:PGPASSWORD = $oldPassword
        } else {
            Remove-Item -LiteralPath 'Env:PGPASSWORD' -ErrorAction SilentlyContinue
        }
        if ($hadConnectTimeout) {
            $env:PGCONNECT_TIMEOUT = $oldConnectTimeout
        } else {
            Remove-Item -LiteralPath 'Env:PGCONNECT_TIMEOUT' -ErrorAction SilentlyContinue
        }
        if ($hadHistory) {
            $env:PSQL_HISTORY = $oldHistory
        } else {
            Remove-Item -LiteralPath 'Env:PSQL_HISTORY' -ErrorAction SilentlyContinue
        }
    }
}

function Set-EnvironmentValue {
    param([string[]]$Lines, [string]$Name, [string]$Value)
    $result = New-Object Collections.Generic.List[string]
    $pattern = "^\s*$([Regex]::Escape($Name))\s*="
    $replaced = $false
    foreach ($line in $Lines) {
        if ($line -match $pattern) {
            if (-not $replaced) {
                $result.Add("$Name=$Value")
                $replaced = $true
            }
        } else {
            $result.Add($line)
        }
    }
    if (-not $replaced) { $result.Add("$Name=$Value") }
    return $result.ToArray()
}

function Set-RestrictedFileAcl {
    param([string]$Path, [switch]$AllowLocalServiceRead)
    $systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $localServiceSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-19')
    $administratorsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetOwner($administratorsSid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($systemSid, $administratorsSid)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow
        ))
    }
    if ($AllowLocalServiceRead) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $localServiceSid,
            [Security.AccessControl.FileSystemRights]'Read, Synchronize',
            [Security.AccessControl.AccessControlType]::Allow
        ))
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Set-RestrictedDirectoryAcl {
    param([string]$Path)
    $systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $administratorsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($administratorsSid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($systemSid, $administratorsSid)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        ))
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Set-ApplicationRootAcl {
    param([string]$Path)
    $systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $localServiceSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-19')
    $administratorsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($administratorsSid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($systemSid, $administratorsSid)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        ))
    }
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $localServiceSid,
        [Security.AccessControl.FileSystemRights]'ReadAndExecute, Synchronize',
        [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    ))
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Set-ApplicationWritableDirectoryAcl {
    param([string]$Path)
    $systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $localServiceSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-19')
    $administratorsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($administratorsSid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($systemSid, $administratorsSid)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        ))
    }
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $localServiceSid,
        [Security.AccessControl.FileSystemRights]::Modify,
        [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    ))
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function New-SecretKey {
    $bytes = New-Object byte[] 48
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Write-InstallLog {
    param([string]$Path, [string]$Message)
    $timestamp = [DateTime]::UtcNow.ToString('o')
    Add-Content -LiteralPath $Path -Value "$timestamp $Message" -Encoding UTF8
}

# Preflight checks do not modify the server.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Windows Administrator.'
}

$root = [IO.Path]::GetFullPath($InstallRoot)
$driveRoot = [IO.Path]::GetPathRoot($root)
$systemRoot = [IO.Path]::GetFullPath($env:SystemRoot)
if (
    $root.TrimEnd('\') -ieq $driveRoot.TrimEnd('\') -or
    $root.TrimEnd('\') -ieq $systemRoot.TrimEnd('\')
) {
    throw 'InstallRoot must be a dedicated application directory.'
}

$resolvedWinSwPath = if (Test-Path -LiteralPath $WinSwPath -PathType Leaf) {
    (Resolve-Path -LiteralPath $WinSwPath).Path
} else {
    throw "WinSW executable not found: $WinSwPath"
}
if (-not (Test-PortableExecutable -Path $resolvedWinSwPath)) {
    throw 'WinSwPath must point to a valid Windows PE executable with an .exe extension.'
}
$winSwHash = (Get-FileHash -LiteralPath $resolvedWinSwPath -Algorithm SHA256).Hash

try {
    $pythonVersionOutput = & $PythonExecutable -c `
        'import sys; print(sys.version_info[0], sys.version_info[1], sys.version_info[2])' `
        2>$null
    $pythonVersionExitCode = $LASTEXITCODE
    $pythonVersionText = $pythonVersionOutput | Select-Object -First 1
    if ($pythonVersionExitCode -ne 0 -or -not $pythonVersionText) {
        throw 'Python did not return a version.'
    }
    $pythonVersionParts = $pythonVersionText.Trim() -split '\s+'
    if ($pythonVersionParts.Count -ne 3) { throw 'Python returned an invalid version.' }
    $pythonVersion = [Version](
        "$($pythonVersionParts[0]).$($pythonVersionParts[1]).$($pythonVersionParts[2])"
    )
} catch {
    throw "Python could not be started with '$PythonExecutable'. Install Python 3.11 or newer."
}
if ($pythonVersion -lt [Version]'3.11') {
    throw "Python 3.11 or newer is required. Found $pythonVersion."
}
Write-Host "Python $pythonVersion found."

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$environmentExamplePath = Join-Path $projectRoot '.env.example'
if (-not (Test-Path -LiteralPath $environmentExamplePath -PathType Leaf)) {
    throw "Environment template not found: $environmentExamplePath"
}

$sharedRoot = Join-Path $root 'shared'
$environmentPath = Join-Path $sharedRoot '.env'
$uploadsPath = Join-Path $sharedRoot 'uploads'
$releasesRoot = Join-Path $root 'releases'
$backupsRoot = Join-Path $root 'backups'
$logsRoot = Join-Path $root 'logs'
$runtimeTemp = Join-Path $sharedRoot 'runtime-temp'
$venvRoot = Join-Path $root '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$serviceExecutable = Join-Path $root "$ServiceName.exe"
$serviceConfiguration = Join-Path $root "$ServiceName.xml"
$environmentExists = Test-Path -LiteralPath $environmentPath -PathType Leaf

if ($environmentExists) {
    $databaseUrl = Read-DotEnvValue -Path $environmentPath -Name 'DATABASE_URL'
    if (-not $databaseUrl) {
        throw 'DATABASE_URL is missing from the existing shared .env file.'
    }
    $database = Resolve-DatabaseParts -DatabaseUrl $databaseUrl
} else {
    $DatabaseHost = $DatabaseHost.Trim()
    $DatabaseName = $DatabaseName.Trim()
    $DatabaseUsername = $DatabaseUsername.Trim()
    if (-not $DatabaseHost) { throw 'PostgreSQL host cannot be empty.' }
    if ($DatabasePort -lt 1) { throw 'PostgreSQL port must be a number from 1 to 65535.' }
    if (-not $DatabaseName) { throw 'PostgreSQL database cannot be empty.' }
    if (-not $DatabaseUsername) { throw 'PostgreSQL username cannot be empty.' }
    if (-not $DatabasePassword) { throw 'PostgreSQL password cannot be empty.' }
    $databasePasswordPlaintext = ConvertFrom-SecureValue `
        -SecureValue $DatabasePassword
    if (-not $databasePasswordPlaintext) {
        throw 'PostgreSQL password cannot be empty.'
    }
    $database = [ordered]@{
        Host = $DatabaseHost
        Port = $DatabasePort
        Username = $DatabaseUsername
        Password = $databasePasswordPlaintext
        Database = $DatabaseName
    }
}

$psqlExecutable = Find-PsqlExecutable
Test-PostgreSqlConnection -PsqlExecutable $psqlExecutable -Database $database
Write-Host 'PostgreSQL connection verified.'

# All preflight checks have passed. Filesystem changes begin here.
$createdDirectories = @{}
foreach ($directory in @(
    $root, $sharedRoot, $uploadsPath, $runtimeTemp, $releasesRoot, $backupsRoot,
    $logsRoot
)) {
    if (Test-Path -LiteralPath $directory -PathType Container) {
        $createdDirectories[$directory] = $false
        Write-Host "Directory already exists; left unchanged: $directory"
    } else {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $createdDirectories[$directory] = $true
        Write-Host "Directory created: $directory"
    }
}

Set-ApplicationRootAcl -Path $root
Set-RestrictedDirectoryAcl -Path $backupsRoot
Set-ApplicationWritableDirectoryAcl -Path $uploadsPath
Set-ApplicationWritableDirectoryAcl -Path $runtimeTemp
Set-ApplicationWritableDirectoryAcl -Path $logsRoot
$installLogPath = Join-Path $logsRoot 'install-server.log'
Write-InstallLog -Path $installLogPath -Message "WinSW SHA-256: $winSwHash"
Write-InstallLog -Path $installLogPath -Message "Python version: $pythonVersion"

if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    Write-Host "Virtual environment already exists; left unchanged: $venvRoot"
} elseif (Test-Path -LiteralPath $venvRoot) {
    throw (
        "The virtual environment directory exists but is incomplete: $venvRoot. " +
        'Move or repair it, then run the installer again.'
    )
} else {
    & $PythonExecutable -m venv $venvRoot
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw 'Could not create the production virtual environment.'
    }
    Write-Host "Virtual environment created: $venvRoot"
}

if ($environmentExists) {
    Write-Host "Environment file already exists; left completely unchanged: $environmentPath"
} else {
    $urlHost = if ($database.Host.Contains(':') -and -not $database.Host.StartsWith('[')) {
        "[$($database.Host)]"
    } else {
        $database.Host
    }
    $encodedUsername = [Uri]::EscapeDataString([string]$database.Username)
    $encodedPassword = [Uri]::EscapeDataString([string]$database.Password)
    $encodedDatabase = [Uri]::EscapeDataString([string]$database.Database)
    $databaseUrl = "postgresql://$encodedUsername`:$encodedPassword@$urlHost`:$($database.Port)/$encodedDatabase"
    $secretKey = New-SecretKey
    $environmentLines = Get-Content -LiteralPath $environmentExamplePath
    $environmentLines = Set-EnvironmentValue $environmentLines 'ENVIRONMENT' 'production'
    $environmentLines = Set-EnvironmentValue $environmentLines 'SECRET_KEY' $secretKey
    $environmentLines = Set-EnvironmentValue $environmentLines 'DATABASE_URL' $databaseUrl
    $environmentLines = Set-EnvironmentValue $environmentLines 'UPLOAD_DIR' $uploadsPath
    $environmentLines = Set-EnvironmentValue $environmentLines 'APP_HOST' '0.0.0.0'
    $environmentLines = Set-EnvironmentValue $environmentLines 'APP_PORT' ([string]$Port)
    $environmentLines = Set-EnvironmentValue $environmentLines 'PUBLIC_BASE_URL' `
        "http://127.0.0.1:$Port"
    $environmentLines = Set-EnvironmentValue $environmentLines 'SESSION_HTTPS_ONLY' 'false'
    [IO.File]::WriteAllLines(
        $environmentPath,
        $environmentLines,
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host "Environment file created and restricted: $environmentPath"
    $secretKey = $null
    $encodedPassword = $null
    $databaseUrl = $null
}
Set-RestrictedFileAcl -Path $environmentPath -AllowLocalServiceRead
$database.Password = $null
$databasePasswordPlaintext = $null
$DatabasePassword = $null

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "Windows service '$ServiceName' already exists; configuration and registration were left unchanged."
} else {
    if (Test-Path -LiteralPath $serviceExecutable -PathType Leaf) {
        if (-not (Test-PortableExecutable -Path $serviceExecutable)) {
            throw "Existing service executable is not a valid PE file: $serviceExecutable"
        }
        $existingHash = (Get-FileHash -LiteralPath $serviceExecutable -Algorithm SHA256).Hash
        if ($existingHash -ine $winSwHash) {
            throw (
                "A different service executable already exists at $serviceExecutable. " +
                'Remove or preserve it manually, then run the installer again.'
            )
        }
        Write-Host "Matching WinSW executable already exists; left unchanged: $serviceExecutable"
    } elseif (Test-Path -LiteralPath $serviceExecutable) {
        throw "The service executable path is not a file: $serviceExecutable"
    } else {
        Copy-Item -LiteralPath $resolvedWinSwPath -Destination $serviceExecutable
        Write-Host "WinSW executable copied: $serviceExecutable"
    }

    $xmlServiceName = [Security.SecurityElement]::Escape($ServiceName)
    $xmlExecutable = [Security.SecurityElement]::Escape($venvPython)
    $xmlWorkingDirectory = [Security.SecurityElement]::Escape((Join-Path $root 'current'))
    $xmlLogPath = [Security.SecurityElement]::Escape($logsRoot)
    $xmlEnvironmentPath = [Security.SecurityElement]::Escape($environmentPath)
    $xmlRuntimeTemp = [Security.SecurityElement]::Escape($runtimeTemp)
    $xmlContent = @"
<service>
  <id>$xmlServiceName</id>
  <name>$xmlServiceName</name>
  <description>Service Management System web application</description>
  <serviceaccount>
    <domain>NT AUTHORITY</domain>
    <user>LocalService</user>
  </serviceaccount>
  <executable>$xmlExecutable</executable>
  <arguments>serve.py</arguments>
  <workingdirectory>$xmlWorkingDirectory</workingdirectory>
  <env name="SMS_ENV_FILE" value="$xmlEnvironmentPath" />
  <env name="ENVIRONMENT" value="production" />
  <env name="TEMP" value="$xmlRuntimeTemp" />
  <env name="TMP" value="$xmlRuntimeTemp" />
  <env name="PYTHONDONTWRITEBYTECODE" value="1" />
  <logpath>$xmlLogPath</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
  <onfailure action="restart" delay="10 sec" />
  <onfailure action="restart" delay="30 sec" />
  <onfailure action="restart" delay="60 sec" />
</service>
"@
    if (Test-Path -LiteralPath $serviceConfiguration -PathType Leaf) {
        $existingXml = Get-Content -LiteralPath $serviceConfiguration -Raw
        if ($existingXml -cne $xmlContent) {
            throw (
                "A different WinSW configuration already exists at $serviceConfiguration. " +
                'Review it manually, then run the installer again.'
            )
        }
        Write-Host "Matching WinSW configuration already exists; left unchanged: $serviceConfiguration"
    } elseif (Test-Path -LiteralPath $serviceConfiguration) {
        throw "The WinSW configuration path is not a file: $serviceConfiguration"
    } else {
        [IO.File]::WriteAllText(
            $serviceConfiguration,
            $xmlContent,
            [Text.UTF8Encoding]::new($false)
        )
        Write-Host "WinSW configuration written: $serviceConfiguration"
    }

    & $serviceExecutable install
    if ($LASTEXITCODE -ne 0) {
        throw "WinSW could not register Windows service '$ServiceName'."
    }
    if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) {
        throw "WinSW returned successfully, but Windows service '$ServiceName' was not found."
    }
    Write-Host "Windows service '$ServiceName' registered."
}

Write-InstallLog -Path $installLogPath -Message 'Server installation completed.'
Write-Host ''
Write-Host "The Windows service was not started because no release is deployed at $(Join-Path $root 'current')."
Write-Host 'The graphical installer will deploy the release and finish configuration.'
