param([ValidateSet('start', 'serve', 'worker', 'init-db')][string]$Mode = 'start')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & python -m hermeneut.research.cli $Mode
    if ($LASTEXITCODE -ne 0) { throw "Research command failed: $Mode" }
} finally {
    Pop-Location
}
