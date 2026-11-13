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
$py = (Get-Command python -ErrorAction Stop).Source
$env:PYTHONIOENCODING = 'utf-8'
while ($true) {
  if ((Test-Path $log) -and (Get-Item $log).Length -gt 5MB) { Move-Item $log "$log.old" -Force }
  "$(Get-Date -Format s) starting runner" | Out-File -Append -Encoding utf8 $log
  # cmd's own redirection keeps Python's UTF-8 bytes as they are (PowerShell 5.1 would re-encode them).
  cmd /c "`"$py`" -u `"$runner`" >> `"$log`" 2>&1"
  "$(Get-Date -Format s) runner stopped (exit $LASTEXITCODE); restarting in 30 s" | Out-File -Append -Encoding utf8 $log
  Start-Sleep -Seconds 30
}
