[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function New-Label {
    param([string]$Text, [int]$X, [int]$Y, [int]$Width = 500)
    $control = [Windows.Forms.Label]::new()
    $control.Text = $Text
    $control.Location = [Drawing.Point]::new($X, $Y)
    $control.Size = [Drawing.Size]::new($Width, 24)
    return $control
}

function New-TextBox {
    param([int]$X, [int]$Y, [int]$Width = 330, [switch]$Password)
    $control = [Windows.Forms.TextBox]::new()
    $control.Location = [Drawing.Point]::new($X, $Y)
    $control.Size = [Drawing.Size]::new($Width, 24)
    $control.UseSystemPasswordChar = $Password
    return $control
}

function Add-Field {
    param(
        [Windows.Forms.Control]$Page,
        [string]$Label,
        [int]$Y,
        [string]$Default = '',
        [switch]$Password,
        [int]$Width = 330
    )
    $Page.Controls.Add((New-Label -Text $Label -X 35 -Y $Y -Width 210))
    $box = New-TextBox -X 250 -Y ($Y - 2) -Width $Width -Password:$Password
    $box.Text = $Default
    $Page.Controls.Add($box)
    return $box
}

function Convert-ToSecureStringValue {
    param([string]$Value)
    return ConvertTo-SecureString -String $Value -AsPlainText -Force
}

function Save-FailureState {
    param([string]$InstallRoot, [string]$Message)
    $stateRoot = Join-Path $env:ProgramData 'ServiceManagementSystem\Installer'
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    $statePath = Join-Path $stateRoot 'state.json'
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { return }
    $lastCompletedStep = 'bundle_verified'
    try {
        $existingState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ([string]$existingState.install_root.TrimEnd('\') -ine
            [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')) { return }
        if ($existingState.last_completed_step) {
            $lastCompletedStep = [string]$existingState.last_completed_step
        }
    } catch { return }
    [ordered]@{
        status = 'failed'
        install_root = $InstallRoot
        last_completed_step = $lastCompletedStep
        message = $Message
        updated_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
}

if (-not (Test-IsAdministrator)) {
    [Windows.Forms.MessageBox]::Show(
        'Run Setup-ServiceManagement.cmd and approve the Windows Administrator prompt.',
        'Administrator access required',
        'OK',
        'Error'
    ) | Out-Null
    exit 1
}

$bundleRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$installer = Join-Path $bundleRoot 'Install-Offline.ps1'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    [Windows.Forms.MessageBox]::Show(
        'Install-Offline.ps1 is missing. Extract the complete offline ZIP and try again.',
        'Incomplete setup package', 'OK', 'Error'
    ) | Out-Null
    exit 1
}

$form = [Windows.Forms.Form]::new()
$form.Text = 'Afaqy Service Management Setup'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = [Drawing.Size]::new(720, 540)
$form.MinimumSize = [Drawing.Size]::new(736, 579)
$form.Font = [Drawing.Font]::new('Segoe UI', 10)
$form.MaximizeBox = $false

$title = New-Label -Text 'Afaqy Service Management Setup' -X 28 -Y 18 -Width 650
$title.Font = [Drawing.Font]::new('Segoe UI Semibold', 18)
$form.Controls.Add($title)

$tabs = [Windows.Forms.TabControl]::new()
$tabs.Location = [Drawing.Point]::new(18, 60)
$tabs.Size = [Drawing.Size]::new(684, 410)
$tabs.Appearance = 'FlatButtons'
$tabs.ItemSize = [Drawing.Size]::new(0, 1)
$tabs.SizeMode = 'Fixed'
$form.Controls.Add($tabs)

$welcome = [Windows.Forms.TabPage]::new()
$databasePage = [Windows.Forms.TabPage]::new()
$adminPage = [Windows.Forms.TabPage]::new()
$installPage = [Windows.Forms.TabPage]::new()
$tabs.TabPages.AddRange(@($welcome, $databasePage, $adminPage, $installPage))

$welcome.Controls.Add((New-Label -Text 'Installation options' -X 30 -Y 24 -Width 600))
$welcome.Controls[0].Font = [Drawing.Font]::new('Segoe UI Semibold', 14)
$modeLabel = New-Label -Text 'Action' -X 35 -Y 78 -Width 210
$welcome.Controls.Add($modeLabel)
$mode = [Windows.Forms.ComboBox]::new()
$mode.DropDownStyle = 'DropDownList'
$mode.Items.AddRange(@('New installation', 'Repair existing installation'))
$mode.SelectedIndex = 0
$mode.Location = [Drawing.Point]::new(250, 76)
$mode.Size = [Drawing.Size]::new(330, 24)
$welcome.Controls.Add($mode)
$installRoot = Add-Field -Page $welcome -Label 'Installation folder' -Y 120 `
    -Default 'C:\ServiceManagement'
$servicePort = Add-Field -Page $welcome -Label 'Application port' -Y 162 -Default '8993'
$welcome.Controls.Add((New-Label -Text (
    'Setup installs missing prerequisites, configures the Windows service, ' +
    'creates the database and adds the local Service Console shortcuts.'
) -X 35 -Y 220 -Width 570))
$welcome.Controls.Add((New-Label -Text (
    'If PostgreSQL is missing, its vendor setup window opens once. Use the same ' +
    'postgres password that you enter on the next page.'
) -X 35 -Y 275 -Width 570))

$databasePage.Controls.Add((New-Label -Text 'PostgreSQL' -X 30 -Y 20 -Width 600))
$databasePage.Controls[0].Font = [Drawing.Font]::new('Segoe UI Semibold', 14)
$dbHost = Add-Field -Page $databasePage -Label 'Server' -Y 62 -Default '127.0.0.1'
$dbPort = Add-Field -Page $databasePage -Label 'Port' -Y 96 -Default '5432'
$postgresUser = Add-Field -Page $databasePage -Label 'Postgres administrator' -Y 130 `
    -Default 'postgres'
$postgresPassword = Add-Field -Page $databasePage -Label 'Postgres password' -Y 164 `
    -Password
$dbName = Add-Field -Page $databasePage -Label 'Application database' -Y 212 `
    -Default 'service_management'
$dbUser = Add-Field -Page $databasePage -Label 'Application database user' -Y 246 `
    -Default 'service_management'
$dbPassword = Add-Field -Page $databasePage -Label 'Application DB password' -Y 280 `
    -Password
$dbPasswordAgain = Add-Field -Page $databasePage -Label 'Confirm DB password' -Y 314 `
    -Password

$adminPage.Controls.Add((New-Label -Text 'First Administrator' -X 30 -Y 24 -Width 600))
$adminPage.Controls[0].Font = [Drawing.Font]::new('Segoe UI Semibold', 14)
$adminPage.Controls.Add((New-Label -Text (
    'Create the account you will use for the first login. More users can be ' +
    'created later from the Users page.'
) -X 35 -Y 65 -Width 580))
$adminFullName = Add-Field -Page $adminPage -Label 'Full name' -Y 125
$adminUsername = Add-Field -Page $adminPage -Label 'Username' -Y 165
$adminPassword = Add-Field -Page $adminPage -Label 'Password' -Y 205 -Password
$adminPasswordAgain = Add-Field -Page $adminPage -Label 'Confirm password' -Y 245 `
    -Password

$installPage.Controls.Add((New-Label -Text 'Ready to install' -X 30 -Y 20 -Width 600))
$installPage.Controls[0].Font = [Drawing.Font]::new('Segoe UI Semibold', 14)
$summary = New-Label -Text '' -X 35 -Y 62 -Width 600
$summary.Height = 62
$installPage.Controls.Add($summary)
$progress = [Windows.Forms.ProgressBar]::new()
$progress.Location = [Drawing.Point]::new(35, 130)
$progress.Size = [Drawing.Size]::new(600, 24)
$progress.Style = 'Marquee'
$progress.Visible = $false
$installPage.Controls.Add($progress)
$status = New-Label -Text 'Click Install to begin.' -X 35 -Y 168 -Width 600
$installPage.Controls.Add($status)
$output = [Windows.Forms.TextBox]::new()
$output.Location = [Drawing.Point]::new(35, 205)
$output.Size = [Drawing.Size]::new(600, 145)
$output.Multiline = $true
$output.ReadOnly = $true
$output.ScrollBars = 'Vertical'
$installPage.Controls.Add($output)

$back = [Windows.Forms.Button]::new()
$back.Text = 'Back'
$back.Location = [Drawing.Point]::new(428, 486)
$back.Size = [Drawing.Size]::new(82, 32)
$back.Enabled = $false
$form.Controls.Add($back)
$next = [Windows.Forms.Button]::new()
$next.Text = 'Next'
$next.Location = [Drawing.Point]::new(520, 486)
$next.Size = [Drawing.Size]::new(82, 32)
$form.Controls.Add($next)
$cancel = [Windows.Forms.Button]::new()
$cancel.Text = 'Cancel'
$cancel.Location = [Drawing.Point]::new(612, 486)
$cancel.Size = [Drawing.Size]::new(82, 32)
$form.Controls.Add($cancel)

$script:installerRunner = $null
$script:installerAsync = $null
$script:installerSharedState = $null
$script:installerLogPath = ''
$script:installerProgressQueue = $null
$script:installerSecrets = @()

function Copy-NewInstallerProgress {
    if (-not $script:installerProgressQueue) { return }
    $line = $null
    while ($script:installerProgressQueue.TryDequeue([ref]$line)) {
        $output.AppendText(([string]$line) + [Environment]::NewLine)
        switch -Wildcard ([string]$line) {
            '*checksums verified*' {
                $status.Text = 'Checking prerequisites and installation files.'
            }
            '*PostgreSQL connection verified*' {
                $status.Text = 'Preparing the application and database.'
            }
            '*Verifying dependencies and deploying*' {
                $status.Text = 'Verifying dependencies. This can take several minutes.'
            }
            '*deployed successfully*' {
                $status.Text = 'Starting and checking the Windows service.'
            }
        }
        $line = $null
    }
    $output.SelectionStart = $output.TextLength
    $output.ScrollToCaret()
}

function Clear-InstallerSecrets {
    $postgresPassword.Clear()
    $dbPassword.Clear()
    $dbPasswordAgain.Clear()
    $adminPassword.Clear()
    $adminPasswordAgain.Clear()
    $script:installerSecrets = @()
}

$installTimer = [Windows.Forms.Timer]::new()
$installTimer.Interval = 250
$installTimer.add_Tick({
    Copy-NewInstallerProgress
    if (-not $script:installerAsync -or
        -not $script:installerAsync.IsCompleted) { return }

    $installTimer.Stop()
    $failure = ''
    try {
        $script:installerRunner.EndInvoke($script:installerAsync) | Out-Null
    } catch {
        $failure = [string]$script:installerSharedState.Error
        if (-not $failure) { $failure = [string]$_.Exception.Message }
    }
    Copy-NewInstallerProgress

    if ($failure) {
        foreach ($secret in $script:installerSecrets) {
            $failure = $failure.Replace($secret, '[REDACTED]')
        }
        Save-FailureState -InstallRoot $installRoot.Text.Trim() -Message $failure
        $status.Text = 'Installation did not complete. Correct the displayed issue and run setup again.'
        if (-not $output.Text.EndsWith($failure + [Environment]::NewLine)) {
            $output.AppendText($failure + [Environment]::NewLine)
        }
    } else {
        $status.Text = 'Installation completed. Open the application or Service Console from the Desktop.'
    }

    $progress.Visible = $false
    $cancel.Text = 'Close'
    $cancel.Enabled = $true
    Clear-InstallerSecrets
    $script:installerRunner.Dispose()
    $script:installerRunner = $null
    $script:installerAsync = $null
    $script:installerSharedState = $null
    $script:installerProgressQueue = $null
})

$mode.add_SelectedIndexChanged({
    $isRepair = $mode.SelectedIndex -eq 1
    foreach ($control in @(
        $dbHost, $dbPort, $postgresUser, $postgresPassword, $dbName, $dbUser,
        $dbPassword, $dbPasswordAgain, $adminFullName, $adminUsername,
        $adminPassword, $adminPasswordAgain
    )) { $control.Enabled = -not $isRepair }
})

$back.add_Click({
    if ($tabs.SelectedIndex -gt 0) { $tabs.SelectedIndex-- }
    $back.Enabled = $tabs.SelectedIndex -gt 0
    $next.Text = if ($tabs.SelectedIndex -eq 3) { 'Install' } else { 'Next' }
})

$cancel.add_Click({ $form.Close() })

$form.add_FormClosing({
    param($sender, $eventArgs)
    if ($script:installerAsync -and -not $script:installerAsync.IsCompleted) {
        $eventArgs.Cancel = $true
        [Windows.Forms.MessageBox]::Show(
            'Setup is still working. Wait for completion before closing this window.',
            'Installation in progress', 'OK', 'Information'
        ) | Out-Null
    }
})

$next.add_Click({
    if ($tabs.SelectedIndex -eq 0) {
        $portValue = 0
        if (-not $installRoot.Text.Trim()) {
            [Windows.Forms.MessageBox]::Show('Choose an installation folder.') | Out-Null
            return
        }
        if (-not [int]::TryParse($servicePort.Text, [ref]$portValue) -or
            $portValue -lt 1 -or $portValue -gt 65535) {
            [Windows.Forms.MessageBox]::Show('Enter a port from 1 to 65535.') | Out-Null
            return
        }
    }
    if ($tabs.SelectedIndex -eq 1 -and $mode.SelectedIndex -eq 0) {
        $dbPortValue = 0
        if (-not [int]::TryParse($dbPort.Text, [ref]$dbPortValue) -or
            $dbPortValue -lt 1 -or $dbPortValue -gt 65535) {
            [Windows.Forms.MessageBox]::Show('Enter a PostgreSQL port from 1 to 65535.') | Out-Null
            return
        }
        if (-not $dbHost.Text.Trim() -or -not $postgresUser.Text.Trim() -or
            -not $postgresPassword.Text -or -not $dbName.Text.Trim() -or
            -not $dbUser.Text.Trim() -or -not $dbPassword.Text) {
            [Windows.Forms.MessageBox]::Show('Complete all PostgreSQL fields.') | Out-Null
            return
        }
        if ($dbPassword.Text -cne $dbPasswordAgain.Text) {
            [Windows.Forms.MessageBox]::Show('The application database passwords do not match.') | Out-Null
            return
        }
    }
    if ($tabs.SelectedIndex -eq 2 -and $mode.SelectedIndex -eq 0) {
        if (-not $adminFullName.Text.Trim() -or -not $adminUsername.Text.Trim()) {
            [Windows.Forms.MessageBox]::Show('Enter the Administrator name and username.') | Out-Null
            return
        }
        if ($adminPassword.Text.Length -lt 8) {
            [Windows.Forms.MessageBox]::Show('The Administrator password must contain at least 8 characters.') | Out-Null
            return
        }
        if ($adminPassword.Text -cne $adminPasswordAgain.Text) {
            [Windows.Forms.MessageBox]::Show('The Administrator passwords do not match.') | Out-Null
            return
        }
    }
    if ($tabs.SelectedIndex -lt 3) {
        $tabs.SelectedIndex++
        $back.Enabled = $true
        $next.Text = if ($tabs.SelectedIndex -eq 3) { 'Install' } else { 'Next' }
        if ($tabs.SelectedIndex -eq 3) {
            $action = if ($mode.SelectedIndex -eq 0) { 'New installation' } else { 'Repair' }
            $summary.Text = "$action`r`nFolder: $($installRoot.Text.Trim())`r`nApplication port: $($servicePort.Text)"
        }
        return
    }

    $next.Enabled = $false
    $back.Enabled = $false
    $cancel.Enabled = $false
    $progress.Visible = $true
    $status.Text = 'Installing. Setup is working; do not close this window.'
    $logRoot = Join-Path $env:ProgramData 'ServiceManagementSystem\Installer'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $logPath = Join-Path $logRoot 'setup.log'
    $script:installerLogPath = $logPath
    $script:installerProgressQueue = `
        [Collections.Concurrent.ConcurrentQueue[string]]::new()
    $script:installerSecrets = @(
        $postgresPassword.Text, $dbPassword.Text, $adminPassword.Text
    ) |
        Where-Object { $_ }
    try {
        $arguments = @{
            InstallRoot = $installRoot.Text.Trim()
            Port = [int]$servicePort.Text
            Mode = if ($mode.SelectedIndex -eq 0) { 'New' } else { 'Repair' }
        }
        if ($mode.SelectedIndex -eq 0) {
            $arguments.DatabaseAdminHost = $dbHost.Text.Trim()
            $arguments.DatabaseAdminPort = [int]$dbPort.Text
            $arguments.DatabaseAdminUsername = $postgresUser.Text.Trim()
            $arguments.DatabaseAdminPassword = Convert-ToSecureStringValue $postgresPassword.Text
            $arguments.DatabaseName = $dbName.Text.Trim()
            $arguments.DatabaseUsername = $dbUser.Text.Trim()
            $arguments.DatabasePassword = Convert-ToSecureStringValue $dbPassword.Text
            $arguments.AdministratorFullName = $adminFullName.Text.Trim()
            $arguments.AdministratorUsername = $adminUsername.Text.Trim()
            $arguments.AdministratorPassword = Convert-ToSecureStringValue $adminPassword.Text
            $arguments.InitializeNewDatabase = $true
        }
        $script:installerSharedState = [hashtable]::Synchronized(@{ Error = '' })
        $worker = @'
param(
    $installerPath, $installerArguments, $logPath, $secrets,
    $sharedState, $progressQueue
)
$ErrorActionPreference = 'Stop'
function Write-InstallerLogLine {
    param([string]$Path, [string]$Value)
    try {
        Add-Content -LiteralPath $Path -Value $Value -Encoding UTF8
    } catch {
        # A log viewer or antivirus scanner must never abort a deployment.
        $progressQueue.Enqueue('Warning: Setup could not append one progress line to setup.log.')
    }
}
try {
    & $installerPath @installerArguments *>&1 | ForEach-Object {
        $line = [string]$_
        foreach ($secret in $secrets) {
            $line = $line.Replace($secret, '[REDACTED]')
        }
        $progressQueue.Enqueue($line)
        Write-InstallerLogLine -Path $logPath -Value $line
    }
} catch {
    $message = [string]$_.Exception.Message
    $position = [string]$_.InvocationInfo.PositionMessage
    $stack = [string]$_.ScriptStackTrace
    if ($position) { $message += [Environment]::NewLine + $position.Trim() }
    if ($stack) {
        $message += [Environment]::NewLine + 'PowerShell stack: ' + $stack.Trim()
    }
    foreach ($secret in $secrets) {
        $message = $message.Replace($secret, '[REDACTED]')
    }
    $sharedState.Error = $message
    $progressQueue.Enqueue($message)
    Write-InstallerLogLine -Path $logPath -Value $message
    throw
}
'@
        $script:installerRunner = [PowerShell]::Create()
        [void]$script:installerRunner.AddScript($worker).
            AddArgument($installer).
            AddArgument($arguments).
            AddArgument($logPath).
            AddArgument($script:installerSecrets).
            AddArgument($script:installerSharedState).
            AddArgument($script:installerProgressQueue)
        $script:installerAsync = $script:installerRunner.BeginInvoke()
        $installTimer.Start()
    } catch {
        $message = [string]$_.Exception.Message
        foreach ($secret in $script:installerSecrets) {
            $message = $message.Replace($secret, '[REDACTED]')
        }
        Add-Content -LiteralPath $logPath -Value $message -Encoding UTF8
        Save-FailureState -InstallRoot $installRoot.Text.Trim() -Message $message
        $progress.Visible = $false
        $status.Text = 'Installation did not complete. Correct the displayed issue and run setup again.'
        $output.AppendText($message + [Environment]::NewLine)
        $cancel.Text = 'Close'
        $cancel.Enabled = $true
        Clear-InstallerSecrets
        if ($script:installerRunner) {
            $script:installerRunner.Dispose()
            $script:installerRunner = $null
        }
        $script:installerAsync = $null
        $script:installerSharedState = $null
        $script:installerProgressQueue = $null
    }
})

[void]$form.ShowDialog()
