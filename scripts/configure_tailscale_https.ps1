$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Port = 8000
$Tailscale = Get-Command tailscale -ErrorAction SilentlyContinue

if (-not $Tailscale) {
  throw "tailscale command was not found. Install Tailscale and log in first."
}

Set-Location $ProjectRoot

$statusText = & $Tailscale.Source status --json
$dnsMatch = [regex]::Match($statusText, '"DNSName"\s*:\s*"([^"]+)"')
if (-not $dnsMatch.Success) {
  throw "Tailscale MagicDNS name was not found. Enable MagicDNS in Tailscale and try again."
}

$dnsName = ([string]$dnsMatch.Groups[1].Value).TrimEnd(".")
$httpsUrl = "https://$dnsName/"

Write-Host "Configuring Tailscale Serve for AI Plantgraphy..."
Write-Host "Target: http://127.0.0.1:$Port"
$serveJob = Start-Job -ScriptBlock {
  param($TailscaleExe, $ServePort)
  & $TailscaleExe serve --bg --yes --https=443 "localhost:$ServePort"
} -ArgumentList $Tailscale.Source, $Port

if (Wait-Job $serveJob -Timeout 45) {
  Receive-Job $serveJob | Out-Host
} else {
  Stop-Job $serveJob -ErrorAction SilentlyContinue
  Remove-Job $serveJob -Force -ErrorAction SilentlyContinue
  throw "Tailscale Serve setup timed out. Enable MagicDNS and HTTPS Certificates in the Tailscale admin console, then run this script again."
}
Remove-Job $serveJob -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Tailscale HTTPS URL:"
Write-Host $httpsUrl
Write-Host ""
Write-Host "Upload:"
Write-Host "$($httpsUrl)upload"
Write-Host ""
Write-Host "Status:"
& $Tailscale.Source serve status
