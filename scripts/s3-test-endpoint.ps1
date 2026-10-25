# Local S3-compatible endpoint for object-store acceptance (SeaweedFS gateway).
#
# This is a real object server speaking the S3 HTTP API on loopback. It is still not the
# institution's object storage: bucket versioning, retention policy, replication and access
# control must be verified on the target service.
#
#   pwsh scripts/s3-test-endpoint.ps1 -Action start
#   pwsh scripts/s3-test-endpoint.ps1 -Action status
#   pwsh scripts/s3-test-endpoint.ps1 -Action stop
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action = 'status',
    [string]$WeedHome = 'tmp/research-services/seaweedfs',
    [int]$MasterPort = 45800,
    [int]$VolumePort = 45801,
    [int]$FilerPort = 45802,
    [int]$S3Port = 49000,
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$weeds = Join-Path $root $WeedHome
$weed = Join-Path $weeds 'weed.exe'
$data = Join-Path $weeds 'data'

function Test-S3 {
    try {
        Invoke-WebRequest "http://127.0.0.1:$S3Port/" -UseBasicParsing -TimeoutSec 5 | Out-Null
        return $true
    } catch { return $false }
}

switch ($Action) {
    'status' {
        $running = [bool](Get-NetTCPConnection -State Listen -LocalPort $S3Port -ErrorAction SilentlyContinue)
        [pscustomobject]@{
            Endpoint = "http://127.0.0.1:$S3Port"
            Running = $running
            Responding = if ($running) { Test-S3 } else { $false }
            Binary = $weed
            DataDir = $data
        } | Format-List
    }
    'start' {
        if (-not (Test-Path $weed)) {
            throw "SeaweedFS binary missing: $weed. Download windows_amd64.zip from https://github.com/seaweedfs/seaweedfs/releases into $weeds"
        }
        New-Item -ItemType Directory -Force $data | Out-Null
        if (Test-S3) { Write-Host "S3 endpoint already responding on $S3Port"; return }
        # grpc ports default to port+10000; keep every port below 55535 and outside the
        # Windows excluded ranges (49152-49351, 49410-49609, 50000-50059, 50246-50345).
        Start-Process -FilePath $weed -ArgumentList @(
            'server', "-dir=$data", '-ip=127.0.0.1',
            "-master.port=$MasterPort", "-volume.port=$VolumePort", "-filer.port=$FilerPort",
            "-s3.port=$S3Port", '-s3') `
            -RedirectStandardOutput (Join-Path $weeds 's3.stdout.log') `
            -RedirectStandardError (Join-Path $weeds 's3.stderr.log') -WindowStyle Hidden
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        while ((Get-Date) -lt $deadline) {
            if (Test-S3) { Write-Host "S3 endpoint ready: http://127.0.0.1:$S3Port"; return }
            Start-Sleep -Milliseconds 800
        }
        throw "S3 endpoint did not become ready; inspect $weeds\s3.stderr.log"
    }
    'stop' {
        Get-Process weed -ErrorAction SilentlyContinue | Stop-Process -Force
        Write-Host 'SeaweedFS stopped.'
    }
}
