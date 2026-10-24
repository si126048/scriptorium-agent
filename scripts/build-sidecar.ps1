# PyInstaller must already be installed in the pinned build environment.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path web/dist/index.html)) { throw 'Build web/dist before the backend.' }
python -m PyInstaller hermeneut.spec --distpath src-tauri/bin --workpath desktop-build/pyinstaller-tmp --noconfirm
if ($LASTEXITCODE -ne 0) { throw 'Backend packaging failed.' }
$source = 'src-tauri/bin/hermeneut-backend.exe'
$destination = 'src-tauri/bin/hermeneut-backend-x86_64-pc-windows-msvc.exe'
if (-not (Test-Path $source)) { throw 'Packaged backend missing.' }
Copy-Item -LiteralPath $source -Destination $destination -Force
Write-Host "Sidecar built: $destination"
