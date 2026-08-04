@echo off
setlocal
set "SMS_SETUP_ROOT=%~dp0"
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "$ErrorActionPreference='Stop'; try { $root=[Environment]::GetEnvironmentVariable('SMS_SETUP_ROOT'); Get-ChildItem -LiteralPath $root -Recurse -File | Unblock-File -ErrorAction SilentlyContinue; $script=Join-Path $root 'Setup-ServiceManagement.ps1'; $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',('"' + $script + '"')); $process=Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -Wait -PassThru; exit $process.ExitCode } catch { Write-Host 'Setup was not started. Approve the Windows Administrator prompt and try again.'; exit 1 }"
exit /b %errorlevel%
