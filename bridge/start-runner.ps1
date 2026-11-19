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
$candidates = @(Get-Command python -All -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq 'Application' } | ForEach-Object { $_.Source })
$candidates += @("$env:LOCALAPPDATA\Python\bin\python.exe") | Where-Object { Test-Path $_ }
$py = $null
foreach ($c in ($candidates | Select-Object -Unique)) {
  & $c -c "import requests, bs4" 2>$null
  if ($LASTEXITCODE -eq 0) { $py = $c; break }
}
if (-not $py) { $py = $candidates[0]; "$(Get-Date -Format s) WARNING: no Python on this PC has requests and beautifulsoup4 installed; using $py" | Out-File -Append -Encoding utf8 $log }
if (-not $py) { throw 'No Python found.' }
$env:PYTHONIOENCODING = 'utf-8'
while ($true) {
  if ((Test-Path $log) -and (Get-Item $log).Length -gt 5MB) { Move-Item $log "$log.old" -Force }
  "$(Get-Date -Format s) starting runner with $py" | Out-File -Append -Encoding utf8 $log
  # cmd's own redirection keeps Python's UTF-8 bytes as they are (PowerShell 5.1 would re-encode them).
  cmd /c "`"$py`" -u `"$runner`" >> `"$log`" 2>&1"
  "$(Get-Date -Format s) runner stopped (exit $LASTEXITCODE); restarting in 30 s" | Out-File -Append -Encoding utf8 $log
  Start-Sleep -Seconds 30
}
