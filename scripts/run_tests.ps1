$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $Python)) {
  throw ".venv was not found. Run scripts\install_windows.ps1 first."
}

& $Python -m unittest discover -s ".\server\tests" -p "test_*.py"
& $Python -m compileall ".\server" ".\scripts"
