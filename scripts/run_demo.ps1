param([double]$DurationSeconds = 60)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Create .venv and install the project first; see README." }
& .\.venv\Scripts\python.exe -m tankdaq run --config configs\demo.yaml --backend sim --duration $DurationSeconds
exit $LASTEXITCODE
