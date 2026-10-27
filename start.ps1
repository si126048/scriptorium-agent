param(
    [ValidateSet('doctor','mcp','acp')][string]$Protocol = 'doctor',
    [string]$Workspace = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = if (Test-Path '.venv\Scripts\python.exe') { Join-Path $PSScriptRoot '.venv\Scripts\python.exe' } else { 'python' }
if ($Protocol -eq 'doctor') { & $python -m scriptorium.plugin doctor }
else { & $python -m scriptorium.plugin $Protocol --workspace $Workspace }
exit $LASTEXITCODE
