$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Requirements = Join-Path $ProjectRoot "server\requirements.txt"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$EnvPath = Join-Path $ProjectRoot ".env"

Set-Location $ProjectRoot

function Find-Python {
  $python = Get-Command py -ErrorAction SilentlyContinue
  if ($python) {
    return @("py", "-3")
  }

  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return @("python")
  }

  throw "Python was not found. Install Python 3.12 or later and run this script again."
}

function New-ApiKey {
  $bytes = New-Object byte[] 24
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

$pythonCommand = Find-Python

if (-not (Test-Path $VenvPython)) {
  Write-Host "Creating virtual environment..."
  if ($pythonCommand.Length -gt 1) {
    & $pythonCommand[0] $pythonCommand[1..($pythonCommand.Length - 1)] -m venv .venv
  } else {
    & $pythonCommand[0] -m venv .venv
  }
}

Write-Host "Installing Python packages..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r $Requirements

if (-not (Test-Path $EnvPath)) {
  Write-Host "Creating .env..."
  Copy-Item $EnvExample $EnvPath
}

$envText = Get-Content -Raw -Path $EnvPath
if ($envText -match "PLANT_DEX_API_KEY=change-me") {
  $envText = $envText.Replace("PLANT_DEX_API_KEY=change-me", "PLANT_DEX_API_KEY=$(New-ApiKey)")
  Set-Content -Path $EnvPath -Value $envText -Encoding UTF8 -NoNewline
}

Write-Host ""
Write-Host "Setup completed."
Write-Host "Start: powershell -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\start_plant_dex.ps1`""
