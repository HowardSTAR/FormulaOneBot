param(
    [string]$Destination = 'D:\backup - f1',
    [string]$Source = 'root@85.198.68.135',
    [string]$RemoteDirectory = '/root/FormulaOneBot/data/backups',
    [string]$Identity = ''
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Destination)) {
    New-Item -ItemType Directory -Path $Destination | Out-Null
}
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv-codex\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
}
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python environment is required' }
$scriptPath = Join-Path $PSScriptRoot 'backup_pull.py'
$arguments = '"{0}" --source "{1}" --remote-dir "{2}" --destination "{3}"' -f $scriptPath, $Source, $RemoteDirectory, $Destination
if ($Identity) { $arguments += ' --identity "{0}"' -f $Identity }
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'TurboTears backup pull' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Output 'TurboTears backup pull installed (every 15 minutes while signed in).'
