<#
  Run this yourself once, after `python bridge/runner.py check` says "Connected".
  It adds a Windows scheduled task that starts the HQ bridge runner, hidden, every time
  you log on (and starts it now). Remove it any time with:
      Unregister-ScheduledTask -TaskName 'DSE Toolkit runner' -Confirm:$false
#>
# Packages the tools need, tzdata included (Windows has no time zone data; without it Herald holds every email). Free.
$req = Join-Path (Split-Path $PSScriptRoot -Parent) 'requirements.txt'
if (Test-Path $req) { python -m pip install --quiet -r $req }
else { python -m pip install --quiet requests beautifulsoup4 tzdata }
$script = Join-Path $PSScriptRoot 'start-runner.ps1'
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'DSE Toolkit runner' -Action $action -Trigger $trigger -Settings $set -Description 'Runs DSE Toolkit tools for jobs queued in DBI Citadel (HQ Tools page)' -Force | Out-Null
Start-ScheduledTask -TaskName 'DSE Toolkit runner'
Write-Host 'Bridge runner registered and started. Its log: bridge/logs/runner.log'
