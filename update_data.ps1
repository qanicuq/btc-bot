# Refresh BTC/ETH 1-minute data from Binance. Run in PowerShell from this BTC folder:
#   powershell -ExecutionPolicy Bypass -File .\update_data.ps1
# Only downloads files you don't already have. Then ask Claude to rebuild the clean files.
$ProgressPreference='SilentlyContinue'; $i='1m'; $base='https://data.binance.vision/data/spot'
foreach($s in 'BTCUSDT','ETHUSDT'){
  $dir="$PSScriptRoot\$s-$i"; New-Item -ItemType Directory -Force $dir | Out-Null
  $d=Get-Date '2017-08-01'; $first=(Get-Date -Day 1).Date
  while($d -lt $first){ $n="$s-$i-$($d.ToString('yyyy-MM'))"
    if(-not (Test-Path "$dir\$n.zip")){ try{ Invoke-WebRequest "$base/monthly/klines/$s/$i/$n.zip" -OutFile "$dir\$n.zip"; Write-Host "$n ok" } catch {} }
    $d=$d.AddMonths(1) }
  $d=$first
  while($d -lt (Get-Date).Date){ $n="$s-$i-$($d.ToString('yyyy-MM-dd'))"
    if(-not (Test-Path "$dir\$n.zip")){ try{ Invoke-WebRequest "$base/daily/klines/$s/$i/$n.zip" -OutFile "$dir\$n.zip"; Write-Host "$n ok" } catch {} }
    $d=$d.AddDays(1) }
}
Write-Host "Done"
