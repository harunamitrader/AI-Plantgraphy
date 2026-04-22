$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Url = "http://127.0.0.1:8000/settings"
$Port = 8000
$Tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
$LanIp = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
  Sort-Object InterfaceMetric |
  Select-Object -First 1 -ExpandProperty IPAddress)
$TailScaleIp = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object {
    $ip = [System.Net.IPAddress]::Parse($_.IPAddress).GetAddressBytes()
    $ip[0] -eq 100 -and ($ip[1] -ge 64 -and $ip[1] -le 127)
  } |
  Select-Object -First 1 -ExpandProperty IPAddress)
$LanUrl = if ($LanIp) { "http://$($LanIp):$Port/" } else { "http://127.0.0.1:$Port/" }
$TailscaleUrl = if ($TailScaleIp) { "http://$($TailScaleIp):$Port/" } else { "" }
$TailscaleHttpsUrl = ""
if ($Tailscale) {
  try {
    $TailscaleStatusText = & $Tailscale.Source status --json
    $TailscaleDnsMatch = [regex]::Match($TailscaleStatusText, '"DNSName"\s*:\s*"([^"]+)"')
    if ($TailscaleDnsMatch.Success) {
      $TailscaleDnsName = [string]$TailscaleDnsMatch.Groups[1].Value
      $TailscaleDnsName = $TailscaleDnsName.TrimEnd(".")
      $TailscaleHttpsUrl = "https://$TailscaleDnsName/"
    }
  } catch {
    $TailscaleHttpsUrl = ""
  }
}

Set-Location $ProjectRoot

$connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
$processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($processId in $processIds) {
  if ($processId -and $processId -ne $PID) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }
}

Start-Sleep -Seconds 1

Start-Process powershell.exe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-Command",
  "cd '$ProjectRoot'; Write-Host 'Plant Dex connect: $Url'; Write-Host 'Plant Dex Wi-Fi: $LanUrl'; if ('$TailscaleUrl') { Write-Host 'Plant Dex Tailscale: $TailscaleUrl' }; & '$Python' -m uvicorn server.app.main:app --host 0.0.0.0 --port 8000"
)

$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline) {
  try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Method Get -TimeoutSec 2
    if ($health.status -eq "ok") {
      if ($Tailscale) {
        try {
          $serveStatusText = & $Tailscale.Source serve status --json
          if ($serveStatusText.Trim() -eq "{}") {
            $serveJob = Start-Job -ScriptBlock {
              param($TailscaleExe, $ServePort)
              & $TailscaleExe serve --bg --yes --https=443 "localhost:$ServePort"
            } -ArgumentList $Tailscale.Source, $Port

            if (Wait-Job $serveJob -Timeout 12) {
              Receive-Job $serveJob | Out-Host
              if ($TailscaleHttpsUrl) {
                Write-Host "Plant Dex Tailscale HTTPS: $TailscaleHttpsUrl"
              }
            } else {
              Stop-Job $serveJob -ErrorAction SilentlyContinue
              Write-Host "Tailscale Serve setup timed out. Open /settings and check the Tailscale HTTPS status."
            }
            Remove-Job $serveJob -Force -ErrorAction SilentlyContinue
          } else {
            if ($TailscaleHttpsUrl) {
              Write-Host "Plant Dex Tailscale HTTPS: $TailscaleHttpsUrl"
            }
          }
        } catch {
          Write-Host "Tailscale Serve setup failed: $($_.Exception.Message)"
        }
      }
      Start-Process $Url
      exit 0
    }
  } catch {
    Start-Sleep -Seconds 1
  }
}

Start-Process $Url
