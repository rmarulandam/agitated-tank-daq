param([switch]$WithNI, [switch]$WithParquet)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Create the environment using an installed Python 3.11+ interpreter; see README." }
}
$extras = @("test")
if ($WithNI) { $extras += "ni" }
if ($WithParquet) { $extras += "parquet" }
$target = ".[" + ($extras -join ",") + "]"
& .\.venv\Scripts\python.exe -m pip install -e $target
if ($LASTEXITCODE -ne 0) { throw "Python package installation failed." }
Write-Host "Installed. The NI driver is a separate installation; this script does not install it."
