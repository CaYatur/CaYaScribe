$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = "C:\Users\cagan\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$venv = Join-Path $root "sidecar\python\.venv"
if (-not (Test-Path $venv)) {
  & $py -m venv $venv
}
& "$venv\Scripts\python.exe" -m pip install -U pip
& "$venv\Scripts\pip.exe" install -e (Join-Path $root "sidecar\python")

Set-Location (Join-Path $root "apps\desktop")
if (-not (Test-Path "node_modules")) { npm install }
npm run tauri -- dev
