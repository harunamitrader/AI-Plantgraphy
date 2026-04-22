$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $ProjectRoot "scripts\start_plant_dex.ps1"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "AI Plantgraphy を起動.lnk"

if (-not (Test-Path $StartScript)) {
  throw "Start script was not found: $StartScript"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-ExecutionPolicy Bypass -File `"$StartScript`""
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.IconLocation = "shell32.dll,13"
$shortcut.Save()

Write-Host "Shortcut created: $ShortcutPath"
