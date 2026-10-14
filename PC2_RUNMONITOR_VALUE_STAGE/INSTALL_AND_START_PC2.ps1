$ErrorActionPreference = "Stop"
$packageDirectory = Split-Path -Parent $PSCommandPath
$applicationPath = Join-Path $packageDirectory "SCADA BONT - PC2 REALTIME SYNC.exe"
$firewallRuleName = "SCADA BONT PC2 Realtime Sync 5001"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments
    exit
}

if (-not (Test-Path -LiteralPath $applicationPath)) {
    throw "File aplikasi PC2 tidak ditemukan: $applicationPath"
}

Get-NetFirewallRule -DisplayName $firewallRuleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
New-NetFirewallRule `
    -DisplayName $firewallRuleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 5001 `
    -LocalAddress "10.100.163.149" `
    -RemoteAddress "10.100.163.150" `
    -Program $applicationPath | Out-Null

Start-Process -FilePath $applicationPath -WorkingDirectory $packageDirectory
Write-Host "SCADA PC2 dijalankan. Sinkronisasi dua arah aktif melalui TCP 5001."
Start-Sleep -Seconds 3
