# Build one current-user NSIS release candidate from one frozen source tree.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
function Assert-Exit([string]$Stage) { if ($LASTEXITCODE -ne 0) { throw "$Stage failed ($LASTEXITCODE)" } }
npm --prefix web ci
Assert-Exit 'npm ci'
npm --prefix web run build:tauri
Assert-Exit 'frontend build'
# The backend also serves the frontend, so freeze web/dist before packaging it.
& (Join-Path $PSScriptRoot 'build-sidecar.ps1')
Assert-Exit 'backend build'
cargo tauri build --config src-tauri/tauri.conf.json --bundles nsis
Assert-Exit 'NSIS build'
Write-Host 'Release candidate built. Clean-user installation and recovery acceptance remain separate.'
