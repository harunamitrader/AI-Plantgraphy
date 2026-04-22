$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $ProjectRoot "scripts\start_plant_dex.ps1"
$ShortcutName = "AI Plantgraphy " + [char]0x3092 + [char]0x8D77 + [char]0x52D5 + ".lnk"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) $ShortcutName

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
