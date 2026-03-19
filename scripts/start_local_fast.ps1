$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateDir = Join-Path $root '.local-dev'
$frontendOutLog = Join-Path $stateDir 'frontend.out.log'
$frontendErrLog = Join-Path $stateDir 'frontend.err.log'
$backendPidFile = Join-Path $stateDir 'backend.pid'
$frontendPidFile = Join-Path $stateDir 'frontend.pid'

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

$frontendDir = Join-Path $root 'web'

if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host 'Installing frontend dependencies (first run)...'
    Push-Location $frontendDir
    try {
        npm.cmd install
    }
    finally {
        Pop-Location
    }
}

if (Test-Path $backendPidFile) {
    $oldPid = Get-Content $backendPidFile -ErrorAction SilentlyContinue
    if ($oldPid) {
        $oldProc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($oldProc) {
            Stop-Process -Id $oldPid -Force
            Write-Host "Stopped local backend PID $oldPid (frontend-only mode)."
        }
    }
    Remove-Item $backendPidFile -Force -ErrorAction SilentlyContinue
}

if (Test-Path $frontendPidFile) {
    $oldPid = Get-Content $frontendPidFile -ErrorAction SilentlyContinue
    if ($oldPid) {
        $oldProc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($oldProc) {
            Stop-Process -Id $oldPid -Force
            Write-Host "Stopped old frontend PID $oldPid before restart."
        }
    }
    Remove-Item $frontendPidFile -Force -ErrorAction SilentlyContinue
}

$frontend = Start-Process -FilePath 'npm.cmd' -ArgumentList @('run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173') -WorkingDirectory $frontendDir -RedirectStandardOutput $frontendOutLog -RedirectStandardError $frontendErrLog -PassThru
$frontend.Id | Set-Content $frontendPidFile

Write-Host ''
Write-Host 'Local dev started:'
Write-Host "- Frontend: http://127.0.0.1:5173 (PID $($frontend.Id))"
Write-Host '- API source for /api: Cloud-hosted via Vite proxy (same DB as web deploy)'
Write-Host ''
Write-Host "Logs: $stateDir"
Write-Host 'Stop local frontend with: ./scripts/stop_local_fast.ps1'
