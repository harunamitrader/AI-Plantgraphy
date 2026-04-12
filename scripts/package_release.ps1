$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $ProjectRoot "dist"
$StagingDir = Join-Path $DistDir "_package"
$Version = Get-Date -Format "yyyyMMdd-HHmmss"
$ZipPath = Join-Path $DistDir "plant-dex-$Version.zip"

$excludePrefixes = @(
  ".git\",
  ".venv\",
  "data\",
  "dist\",
  "temp_workspace\",
  "_tmp\",
  "__pycache__\"
)

$excludeFiles = @(
  ".env"
)

function Get-RelativePath {
  param(
    [string]$BasePath,
    [string]$TargetPath
  )

  $baseUri = New-Object System.Uri (($BasePath.TrimEnd("\") + "\"))
  $targetUri = New-Object System.Uri $TargetPath
  return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString()).Replace("/", "\")
}

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$resolvedDist = (Resolve-Path $DistDir).Path
if ((Test-Path $StagingDir) -and ((Resolve-Path $StagingDir).Path.StartsWith($resolvedDist))) {
  Remove-Item -LiteralPath $StagingDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StagingDir | Out-Null

$files = Get-ChildItem -Recurse -File | Where-Object {
  $relative = Get-RelativePath -BasePath $ProjectRoot -TargetPath $_.FullName
  $excludedByPrefix = $false
  foreach ($prefix in $excludePrefixes) {
    if (
      $relative.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) -or
      $relative.Contains("\__pycache__\")
    ) {
      $excludedByPrefix = $true
      break
    }
  }
  -not $excludedByPrefix -and ($excludeFiles -notcontains $relative) -and ($_.Extension -ne ".pyc")
}

foreach ($file in $files) {
  $relative = Get-RelativePath -BasePath $ProjectRoot -TargetPath $file.FullName
  $target = Join-Path $StagingDir $relative
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
  Copy-Item -LiteralPath $file.FullName -Destination $target
}

Compress-Archive -Path (Join-Path $StagingDir "*") -DestinationPath $ZipPath -Force
Remove-Item -LiteralPath $StagingDir -Recurse -Force
Write-Host "Release package created: $ZipPath"
