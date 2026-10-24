# One reproducible acceptance run for the unified research workbench.
#
# It records the verified version (working-tree digest, not only Git HEAD), the toolchain,
# the database/Elasticsearch actually used, and every check with its own log file. Missing
# integration services are reported as skipped, never as passed.
#
#   $env:SCRIPTORIUM_TEST_DATABASE_URL = 'postgresql+psycopg://USER@127.0.0.1:55432/scriptorium_test'
#   $env:SCRIPTORIUM_TEST_ELASTICSEARCH_URL = 'http://127.0.0.1:59200'
#   pwsh scripts/test-services.ps1 -Action start     # disposable loopback services
#   pwsh scripts/run-acceptance.ps1
#
# Never point the test database URL at a real research database: tests create and drop schemas.
[CmdletBinding()]
param(
    [string]$DatabaseUrl = $env:SCRIPTORIUM_TEST_DATABASE_URL,
    [string]$ElasticsearchUrl = $env:SCRIPTORIUM_TEST_ELASTICSEARCH_URL,
    [string]$OutDir = 'output/acceptance',
    [switch]$SkipFrontend,
    [switch]$SkipDesktop,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$run = Join-Path $root (Join-Path $OutDir $stamp)
New-Item -ItemType Directory -Force -Path $run | Out-Null

$results = [System.Collections.Generic.List[object]]::new()

function Invoke-Step {
    param([string]$Name, [scriptblock]$Command)
    $log = Join-Path $run "$Name.log"
    $clock = [Diagnostics.Stopwatch]::StartNew()
    Write-Host "==> $Name" -ForegroundColor Cyan
    try {
        & $Command *> $log
        $code = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
    } catch {
        $_ | Out-String | Add-Content -Path $log
        $code = 1
    }
    $clock.Stop()
    $results.Add([pscustomobject]@{
        step = $Name
        exit_code = $code
        status = if ($code -eq 0) { 'pass' } else { 'fail' }
        seconds = [math]::Round($clock.Elapsed.TotalSeconds, 1)
        log = (Resolve-Path $log).Path
    })
    Write-Host ("    {0} in {1:N1}s -> {2}" -f $(if ($code -eq 0) { 'pass' } else { 'FAIL' }), $clock.Elapsed.TotalSeconds, $log)
}

function Get-SummaryLine([string]$log) {
    $text = Get-Content -Path $log -Raw -ErrorAction SilentlyContinue
    if (-not $text) { return '' }
    $match = [regex]::Matches($text, '(?m)^=*\s*\d+ (?:passed|failed).*$')
    if ($match.Count) { return $match[$match.Count - 1].Value.Trim() }
    $match = [regex]::Matches($text, '(?m)^\d+ (?:passed|failed).*$')
    if ($match.Count) { return $match[$match.Count - 1].Value.Trim() }
    return ''
}

# ---------------------------------------------------------------- environment record
$env:SCRIPTORIUM_TEST_DATABASE_URL = $DatabaseUrl
$env:SCRIPTORIUM_TEST_ELASTICSEARCH_URL = $ElasticsearchUrl

# The legacy SQLite database is a migration source, not scratch space. Record it before and after
# so a run that writes it can never be mistaken for a clean acceptance run.
$sourceDb = Join-Path $root 'data/lacan.db'
$env:SCRIPTORIUM_FROZEN_SOURCE = $sourceDb
function Get-SourceState {
    $parts = foreach ($suffix in '', '-wal', '-shm') {
        $path = "$sourceDb$suffix"
        if (Test-Path $path) { "$suffix=$(python -c "import hashlib,sys; f=open(sys.argv[1],'rb'); print(hashlib.file_digest(f,'sha256').hexdigest())" $path)" }
        else { "$suffix=absent" }
    }
    return ($parts -join ';')
}
$sourceBefore = Get-SourceState

$snapshot = python scripts/worktree-digest.py --json | ConvertFrom-Json
$safeDatabaseUrl = python -c "import os; from scriptorium.research.config import redacted_service_url; print(redacted_service_url(os.getenv('SCRIPTORIUM_TEST_DATABASE_URL')))"
$safeElasticsearchUrl = python -c "import os; from scriptorium.research.config import redacted_service_url; print(redacted_service_url(os.getenv('SCRIPTORIUM_TEST_ELASTICSEARCH_URL')))"
$envInfo = [ordered]@{
    started_at = (Get-Date).ToString('o')
    root = $root
    python = (python --version 2>&1 | Out-String).Trim()
    node = (node --version 2>&1 | Out-String).Trim()
    npm = (npm --version 2>&1 | Out-String).Trim()
    cargo = (cargo --version 2>&1 | Out-String).Trim()
    git_head = $snapshot.git_head
    git_dirty_files = $snapshot.git_dirty_files
    worktree_files = $snapshot.files
    worktree_digest = $snapshot.digest
    code_files = $snapshot.code_files
    code_digest = $snapshot.code_digest
    test_database_url = $safeDatabaseUrl
    test_elasticsearch_url = $safeElasticsearchUrl
}
$envInfo.GetEnumerator() | ForEach-Object { '{0,-24} {1}' -f $_.Key, $_.Value } | Set-Content -Path (Join-Path $run 'environment.txt')
$envInfo | ConvertTo-Json | Set-Content -Path (Join-Path $run 'environment.json')

try {
    $services = pwsh -NoProfile -File (Join-Path $PSScriptRoot 'test-services.ps1') -Action status 2>&1 | Out-String
    $services | Set-Content -Path (Join-Path $run 'services.txt')
} catch {
    "services status unavailable: $($_.Exception.Message)" | Set-Content -Path (Join-Path $run 'services.txt')
}

# ---------------------------------------------------------------- checks
if (-not $SkipTests) {
    Invoke-Step 'pytest-full' {
        python -m pytest -q --tb=short --durations=10 "--junitxml=$run\junit.xml"
    }
    Invoke-Step 'pytest-research-suite' {
        python -m pytest tests/test_research_texts.py tests/test_research_integration.py tests/test_unified_workspace.py tests/test_research_s3.py tests/test_research_s3_live.py tests/test_research_ocr.py tests/test_research_settings.py tests/test_legacy_matrix.py tests/test_source_guard.py tests/test_research_experience.py -q --tb=short
    }
}
Invoke-Step 'ruff' {
    python -m ruff check scriptorium/research migrations/research scripts tests/test_research_texts.py tests/test_research_integration.py tests/test_unified_workspace.py tests/test_research_s3.py tests/test_research_s3_live.py tests/test_research_ocr.py tests/test_research_settings.py tests/test_legacy_matrix.py tests/test_source_guard.py tests/test_research_experience.py
}
Invoke-Step 'openapi-types' { python scripts/generate-api-types.py --check }
Invoke-Step 'capabilities' {
    python -c "import json,importlib.util; print(json.dumps({'rapidocr': bool(importlib.util.find_spec('rapidocr_onnxruntime')), 'tesseract_binary': bool(__import__('shutil').which('tesseract')), 's3_endpoint_env': bool(__import__('os').environ.get('SCRIPTORIUM_TEST_S3_ENDPOINT'))}, ensure_ascii=False))"
}
if (-not $SkipFrontend) {
    Invoke-Step 'web-build' { npm --prefix web run build }
    Invoke-Step 'web-lint' { npm --prefix web run lint }
}
if (-not $SkipDesktop) {
    Invoke-Step 'cargo-check' { cargo check --offline --manifest-path src-tauri/Cargo.toml }
}

# ---------------------------------------------------------------- summary
$sourceAfter = Get-SourceState
$sourceUnchanged = $sourceBefore -eq $sourceAfter
$endSnapshot = python scripts/worktree-digest.py --json | ConvertFrom-Json
$codeUnchanged = $snapshot.code_digest -eq $endSnapshot.code_digest
$testCounts = $null
if (Test-Path (Join-Path $run 'junit.xml')) {
    [xml]$junit = Get-Content (Join-Path $run 'junit.xml') -Raw
    $testCounts = [ordered]@{ tests = 0; skipped = 0; failures = 0; errors = 0 }
    foreach ($suite in $junit.testsuites.testsuite) {
        foreach ($key in @('tests','skipped','failures','errors')) { $testCounts[$key] += [int]$suite.$key }
    }
}
$complete = (-not $SkipTests -and -not $SkipFrontend -and -not $SkipDesktop -and
    $sourceUnchanged -and $codeUnchanged -and $null -ne $testCounts -and $testCounts.skipped -eq 0 -and
    $testCounts.failures -eq 0 -and $testCounts.errors -eq 0 -and
    ($results | Where-Object { $_.status -ne 'pass' }).Count -eq 0)
@(
    "source       $sourceDb",
    "before       $sourceBefore",
    "after        $sourceAfter",
    $(if ($sourceUnchanged) { 'result       UNCHANGED (the migration source was not written)' }
      else { 'result       CHANGED - something wrote the migration source during this run' })
) | Set-Content -Path (Join-Path $run 'source-database.txt')

$summary = [ordered]@{
    environment = $envInfo
    steps = $results
    test_counts = $testCounts
    code_unchanged = $codeUnchanged
    ending_code_digest = $endSnapshot.code_digest
    automated_verification_complete = $complete
    source_database = [ordered]@{ path = $sourceDb; unchanged = $sourceUnchanged; before = $sourceBefore; after = $sourceAfter }
    notes = @(
        'Skips are not passes: confirm the integration service URLs above are real disposable services.',
        'Cargo check is not a desktop installer build; real S3, scanned OCR, and a fresh environment still need separate runs.',
        'This run does not perform the production data switch or the academic quality review.'
    )
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $run 'summary.json')

$lines = @("# Acceptance run $stamp", '',
    ('- code digest: `{0}` ({1} files; docs excluded)' -f $snapshot.code_digest, $snapshot.code_files),
    ('- worktree digest (with docs): `{0}` ({1} files)' -f $snapshot.digest, $snapshot.files),
    ('- git HEAD: `{0}` with {1} changed paths' -f $snapshot.git_head, $snapshot.git_dirty_files),
    ('- database: `{0}`' -f $envInfo.test_database_url),
    ('- elasticsearch: `{0}`' -f $envInfo.test_elasticsearch_url),
    ('- migration source: {0}' -f $(if ($sourceUnchanged) { '`data/lacan.db` unchanged' } else { '**`data/lacan.db` WAS WRITTEN during this run**' })),
    ('- code unchanged during checks: {0}' -f $codeUnchanged),
    ('- automated verification complete (zero skipped tests): {0}' -f $complete),
    '', '| step | status | seconds | log |', '|---|---|---|---|')
foreach ($row in $results) {
    $lines += ('| {0} | {1} | {2} | `{3}` |' -f $row.step, $row.status, $row.seconds, (Split-Path $row.log -Leaf))
}
$lines += '', '## Counts', ''
foreach ($row in $results) {
    $counts = Get-SummaryLine $row.log
    if ($counts) { $lines += ('- {0}: {1}' -f $row.step, $counts) }
}
$lines | Set-Content -Path (Join-Path $run 'summary.md')

Write-Host ''
Write-Host "Acceptance run written to $run" -ForegroundColor Green
$results | Format-Table step, status, seconds -AutoSize | Out-String | Write-Host
if (($results | Where-Object { $_.status -ne 'pass' }).Count -gt 0 -or -not $sourceUnchanged -or -not $codeUnchanged) {
    Write-Host 'One or more checks failed. See the per-step logs and summary.md.' -ForegroundColor Red
    exit 1
}
if (-not $SkipTests -and $testCounts.skipped -gt 0) {
    Write-Host 'Integration tests were skipped; automated acceptance is incomplete.' -ForegroundColor Yellow
    exit 1
}
exit 0
