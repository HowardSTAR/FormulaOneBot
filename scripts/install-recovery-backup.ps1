param(
    [string]$Config = (Join-Path $PSScriptRoot 'backup-f1.json'),
    [string]$Python = '',
    [switch]$SkipServerRegistration
)
$ErrorActionPreference = 'Stop'
$Config = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$destination = [Environment]::ExpandEnvironmentVariables($settings.windows.destination)
$at = [DateTime]::Today.Add([TimeSpan]::ParseExact($settings.windows.time, 'hh\:mm', [Globalization.CultureInfo]::InvariantCulture))
$age = [Environment]::ExpandEnvironmentVariables($settings.windows.age)
if (-not (Get-Command $age -ErrorAction SilentlyContinue)) {
    throw 'Install age (winget install --id FiloSottile.age), then reopen PowerShell.'
}
if (-not $Python) { $Python = (Get-Command python.exe).Source }
& $Python -c 'import sys; sys.exit(sys.version_info < (3,11))'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
$command = Join-Path $PSScriptRoot 'recovery_backup.py'
& $Python $command --config $Config init-recovery
if ($LASTEXITCODE -ne 0) { throw 'The local recovery identity could not be created.' }
if (-not $SkipServerRegistration) {
    & $Python $command --config $Config register
    if ($LASTEXITCODE -ne 0) { throw 'The backup key could not be registered.' }
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null
& $Python $command --config $Config pull
if ($LASTEXITCODE -ne 0) { throw 'The first backup failed. Check ~/.turbotears-backup/backup.log.' }

$pythonw = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) {
    $pythonw = & $Python -c 'import pathlib,sys; print(pathlib.Path(sys.executable).with_name("pythonw.exe"))'
}
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe is required for silent scheduled runs.' }
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --config "{1}"' -f $command, $Config)
$triggers = @((New-ScheduledTaskTrigger -Daily -At $at), (New-ScheduledTaskTrigger -AtLogOn -User $user))
$options = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 25) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'TurboTears backup pull' -Action $action -Trigger $triggers -Settings $options -Principal $principal -Force | Out-Null
Write-Output "TurboTears backup installed. Daily at $($settings.windows.time) and after sign-in if today's backup is missing."
