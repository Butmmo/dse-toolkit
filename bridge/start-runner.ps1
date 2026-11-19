<#
  Keeps the HQ bridge runner going: starts runner.py, writes its output to
  _tools/bridge/logs/runner.log (UTF-8), and restarts it 30 seconds after it stops.
  install.ps1 makes Windows run this hidden at log-on. Stop it with:
      Stop-ScheduledTask -TaskName 'DSE Toolkit runner'
#>
$here = $PSScriptRoot
$logs = Join-Path $here 'logs'
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs 'runner.log'
$runner = Join-Path $here 'runner.py'
# Which Python? The first one on the PATH is not always the one with our packages (19 Nov 2026: a Python 3.12 without requests and beautifulsoup4
# came first, and every lead tool failed with "No module named requests"). Take the first Python that can import what the tools need.
# On Windows that includes tzdata: Windows has no time zone data of its own, and without it Herald holds every email (19 Nov 2026).
$candidates = @(Get-Command python -All -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq 'Application' } | ForEach-Object { $_.Source })
$candidates += @("$env:LOCALAPPDATA\Python\bin\python.exe") | Where-Object { Test-Path $_ }
$py = $null
foreach ($c in ($candidates | Select-Object -Unique)) {
  & $c -c "import sys, requests, bs4; sys.platform != 'win32' or __import__('tzdata')" 2>$null
  if ($LASTEXITCODE -eq 0) { $py = $c; break }
}
if (-not $py) {
  # none has tzdata: install it (free, pure data) into the first Python that has requests and bs4, then check again
  foreach ($c in ($candidates | Select-Object -Unique)) {
    & $c -c "import requests, bs4" 2>$null
    if ($LASTEXITCODE -eq 0) {
      "$(Get-Date -Format s) tzdata is missing for $c; installing it (pip install tzdata)" | Out-File -Append -Encoding utf8 $log
      & $c -m pip install --quiet tzdata 2>&1 | Out-File -Append -Encoding utf8 $log
      & $c -c "import tzdata" 2>$null
      if ($LASTEXITCODE -eq 0) { $py = $c; break }
      "$(Get-Date -Format s) WARNING: tzdata could not be installed for $c. HERALD WILL HOLD EVERY EMAIL until you run: `"$c`" -m pip install tzdata" | Out-File -Append -Encoding utf8 $log
      $py = $c; break
    }
  }
}
if (-not $py) { $py = $candidates[0]; "$(Get-Date -Format s) WARNING: no Python on this PC has requests and beautifulsoup4 installed; using $py" | Out-File -Append -Encoding utf8 $log }
if (-not $py) { throw 'No Python found.' }
$env:PYTHONIOENCODING = 'utf-8'
while ($true) {
  if ((Test-Path $log) -and (Get-Item $log).Length -gt 5MB) { Move-Item $log "$log.old" -Force }
  "$(Get-Date -Format s) starting runner with $py" | Out-File -Append -Encoding utf8 $log
  # cmd's own redirection keeps Python's UTF-8 bytes as they are (PowerShell 5.1 would re-encode them).
  cmd /c "`"$py`" -u `"$runner`" >> `"$log`" 2>&1"
  $code = $LASTEXITCODE
  # Exit 75 is a deliberate restart (the runner.restart tool): fresh code, not a crash. Any other code is logged as a stop.
  if ($code -eq 75) { "$(Get-Date -Format s) runner restart requested from Citadel (exit 75); starting again in 30 s" | Out-File -Append -Encoding utf8 $log }
  else { "$(Get-Date -Format s) runner stopped (exit $code); restarting in 30 s" | Out-File -Append -Encoding utf8 $log }
  Start-Sleep -Seconds 30
}
