$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# The supervisor has no web controls. A local STOP file is an operator kill switch.
while (-not (Test-Path -LiteralPath "$PSScriptRoot\.garden\STOP")) {
 & "$PSScriptRoot\.venv\Scripts\python.exe" -u "$PSScriptRoot\live_runner.py" *>> "$PSScriptRoot\.garden\service.log"
 if (Test-Path -LiteralPath "$PSScriptRoot\.garden\STOP") { break }
 Start-Sleep -Seconds 30
}
