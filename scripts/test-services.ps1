# Local, disposable PostgreSQL + Elasticsearch used by the acceptance runs.
#
# These are temporary test dependencies under tmp/research-services, bound to loopback only.
# They are not a production deployment: SCRIPTORIUM_TEST_DATABASE_URL must point at a database
# that may be created and dropped, never at real research data.
#
#   pwsh scripts/test-services.ps1 -Action status
#   pwsh scripts/test-services.ps1 -Action start
#   pwsh scripts/test-services.ps1 -Action stop
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action = 'status',
    [string]$ServicesDir = 'tmp/research-services',
    [int]$PostgresPort = 55432,
    [int]$ElasticsearchPort = 59200,
    [int]$PostgresTimeoutSeconds = 60,
    [int]$ElasticsearchTimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$services = Join-Path $root $ServicesDir
$pgBin = Join-Path $services 'pgsql/bin'
$pgData = Join-Path $services 'pg-data'
$esHome = Join-Path $services 'elasticsearch-8.19.3'

function Test-Port([int]$port) {
    $connection = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    return [bool]$connection
}

function Wait-Port([int]$port, [int]$seconds, [string]$label) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port $port) { return $true }
        Start-Sleep -Milliseconds 750
    }
    Write-Warning "$label did not start listening on port $port within $seconds seconds"
    return $false
}

function Get-Status {
    $pgUp = Test-Port $PostgresPort
    $esUp = Test-Port $ElasticsearchPort
    $database = $null
    $cluster = $null
    if ($pgUp) {
        $database = & (Join-Path $pgBin 'psql.exe') -h 127.0.0.1 -p $PostgresPort -U research -d postgres -tAc 'select version()' 2>$null
    }
    if ($esUp) {
        try {
            $cluster = (Invoke-WebRequest -Uri "http://127.0.0.1:$ElasticsearchPort" -UseBasicParsing -TimeoutSec 10).Content | ConvertFrom-Json
            $cluster = "$($cluster.version.number) ($($cluster.cluster_name))"
        } catch { $cluster = "unreachable: $($_.Exception.Message)" }
    }
    [pscustomobject]@{
        PostgreSQL = if ($pgUp) { $database } else { 'stopped' }
        PostgresPort = $PostgresPort
        Elasticsearch = if ($esUp) { $cluster } else { 'stopped' }
        ElasticsearchPort = $ElasticsearchPort
        ServicesDir = $services
    }
}

switch ($Action) {
    'status' { Get-Status | Format-List }

    'start' {
        if (-not (Test-Path $pgData)) { throw "Missing PostgreSQL data directory: $pgData (see docs/research-service.md)" }
        if (-not (Test-Path $esHome)) { throw "Missing Elasticsearch distribution: $esHome" }
        if (Test-Port $PostgresPort) {
            Write-Host "PostgreSQL already listening on $PostgresPort"
        } else {
            $log = Join-Path $services 'postgres.stdout.log'
            & (Join-Path $pgBin 'pg_ctl.exe') -D $pgData -l $log -o "-h 127.0.0.1 -p $PostgresPort" start
            if (-not (Wait-Port $PostgresPort $PostgresTimeoutSeconds 'PostgreSQL')) { throw 'PostgreSQL failed to start' }
            Write-Host "PostgreSQL listening on 127.0.0.1:$PostgresPort"
        }
        if (Test-Port $ElasticsearchPort) {
            Write-Host "Elasticsearch already listening on $ElasticsearchPort"
        } else {
            # The distribution config pins loopback + single-node + security off for this node.
            Start-Process -FilePath (Join-Path $esHome 'bin/elasticsearch.bat') `
                -RedirectStandardOutput (Join-Path $services 'elastic.stdout.log') `
                -RedirectStandardError (Join-Path $services 'elastic.stderr.log') `
                -WindowStyle Hidden
            if (-not (Wait-Port $ElasticsearchPort $ElasticsearchTimeoutSeconds 'Elasticsearch')) {
                throw "Elasticsearch failed to start; inspect $services\elastic.stderr.log"
            }
            Write-Host "Elasticsearch listening on 127.0.0.1:$ElasticsearchPort"
        }
        Get-Status | Format-List
    }

    'stop' {
        if (Test-Port $PostgresPort) {
            & (Join-Path $pgBin 'pg_ctl.exe') -D $pgData -m fast stop
        } else { Write-Host 'PostgreSQL is not running.' }
        if (Test-Port $ElasticsearchPort) {
            $owner = (Get-NetTCPConnection -State Listen -LocalPort $ElasticsearchPort | Select-Object -First 1).OwningProcess
            if ($owner) { Stop-Process -Id $owner -Force; Write-Host "Stopped Elasticsearch process $owner" }
        } else { Write-Host 'Elasticsearch is not running.' }
    }
}
