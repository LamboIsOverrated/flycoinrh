$ErrorActionPreference = 'Stop'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($identity -match 'CodexSandbox') { throw 'Install the service under the real Windows user account.' }
& "$PSScriptRoot\.venv\Scripts\python.exe" -c 'from pilot_wallets import Wallets; assert len(Wallets().verify_signers()) == 10'
if ($LASTEXITCODE -ne 0) { throw 'Wallets cannot be recovered under this account.' }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$PSScriptRoot+'\Start-Garden.ps1"') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'Garden of Flies' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Automatic local garden runner; website visitors only observe.' -Force | Out-Null
Start-ScheduledTask -TaskName 'Garden of Flies'
Write-Output 'Garden service installed and started. It restarts at Windows sign-in.'
