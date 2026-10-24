param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$dataDir = Join-Path $PSScriptRoot 'data'
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Force $dataDir | Out-Null }

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    Write-Warning ".venv not found -- falling back to system python"
    $python = "python"
}

Write-Host "Starting Scriptorium Web UI at http://127.0.0.1:$Port ..." -ForegroundColor Cyan
Write-Host "Python: $python" -ForegroundColor DarkGray
& $python -m uvicorn scriptorium.api:app --host 127.0.0.1 --port $Port
