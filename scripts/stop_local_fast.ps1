$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateDir = Join-Path $root '.local-dev'
$backendPidFile = Join-Path $stateDir 'backend.pid'
$frontendPidFile = Join-Path $stateDir 'frontend.pid'

function Stop-FromPidFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PidFile,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Test-Path $PidFile)) {
        Write-Host "$Name not running (no PID file)."
        return
    }

    $pidValue = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $pidValue) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "$Name PID file empty; cleaned up."
        return
    }

    $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $pidValue -Force
        Write-Host "$Name stopped (PID $pidValue)."
    }
    else {
        Write-Host "$Name already stopped."
    }

    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Stop-FromPidFile -PidFile $backendPidFile -Name 'Backend'
Stop-FromPidFile -PidFile $frontendPidFile -Name 'Frontend'
