[CmdletBinding()]
param(
    [string]$Environment = "staging",
    [string]$WorkerService = "SignalRankAI",
    [string]$EngineService = "striking-optimism",
    [string]$FrontdoorService = "bountiful-miracle",
    [int]$Hours = 24
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($Environment.ToLowerInvariant() -in @("production", "prod")) {
    throw "This command is staging-only."
}
if ($Hours -lt 1) {
    throw "Hours must be at least 1."
}
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    throw "Railway CLI is not installed or not available in PATH."
}

function Invoke-RailwayCapture {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    Write-Host ("railway " + ($Arguments -join " ")) -ForegroundColor DarkGray
    $output = & railway @Arguments 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Railway command failed ($LASTEXITCODE): railway $($Arguments -join ' ')`n$output"
    }
    return $output
}

$hoursToken = "${Hours}h"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$evidenceDir = Join-Path (Get-Location) ("deployment_evidence\soak-" + $stamp)
New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null

& railway whoami
if ($LASTEXITCODE -ne 0) { throw "Railway authentication check failed." }
& railway environment $Environment
if ($LASTEXITCODE -ne 0) { throw "Could not activate Railway environment '$Environment'." }

$services = @($WorkerService, $EngineService, $FrontdoorService)
$forbidden = @(
    'schema_gate BLOCKED',
    'Database schema admission failed',
    'UndefinedTableError',
    'UndefinedColumnError',
    'AmbiguousParameterError',
    'relation does not exist',
    'column does not exist',
    'task crashed:',
    '\[FATAL\]',
    'OutOfMemory',
    'Killed process'
)
$blockerFilter = @(
    '(schema_gate AND BLOCKED)', 'UndefinedTableError', 'UndefinedColumnError',
    'AmbiguousParameterError', 'FATAL', 'OutOfMemory', 'crashed'
) -join ' OR '

$status = Invoke-RailwayCapture -Arguments @("service", "list", "--json")
$statusPath = Join-Path $evidenceDir "railway_service_status.json"
Set-Content -Path $statusPath -Value $status -Encoding UTF8
$serviceStatus = $status | ConvertFrom-Json
$nowUtc = (Get-Date).ToUniversalTime()
foreach ($service in $services) {
    $entry = $serviceStatus | Where-Object { $_.name -eq $service } | Select-Object -First 1
    if ($null -eq $entry) { throw "Railway service status did not include $service." }
    if ($entry.status -ne "SUCCESS" -or $entry.deploymentStopped) {
        throw "$service is not running a successful deployment."
    }
    $createdUtc = [DateTimeOffset]::Parse($entry.latestDeployment.createdAt).UtcDateTime
    $ageHours = ($nowUtc - $createdUtc).TotalHours
    if ($ageHours -lt $Hours) {
        throw ("{0} deployment age is {1:N2}h; a {2}h uninterrupted soak cannot yet be certified." -f $service, $ageHours, $Hours)
    }
}

$serviceEvidence = @{}
foreach ($service in $services) {
    $safeName = $service -replace '[^A-Za-z0-9_.-]', '_'
    $logs = Invoke-RailwayCapture -Arguments @(
        "logs", "-s", $service, "-e", $Environment,
        "--since", $hoursToken, "--lines", "2000"
    )
    $logPath = Join-Path $evidenceDir ("$safeName-soak.log")
    Set-Content -Path $logPath -Value $logs -Encoding UTF8

    $schemaMarker = Invoke-RailwayCapture -Arguments @(
        "logs", "-s", $service, "-e", $Environment, "--since", "7d",
        "--lines", "20", "--filter", "alembic_current=0038_account_security_product"
    )
    $patchMarker = Invoke-RailwayCapture -Arguments @(
        "logs", "-s", $service, "-e", $Environment, "--since", "7d",
        "--lines", "20", "--filter", "patch=deployment-final-r4"
    )
    if (-not $schemaMarker.Contains('alembic_current=0038_account_security_product')) {
        throw "$service did not prove Alembic head 0038 in retained deployment logs."
    }
    if (-not $patchMarker.Contains('patch=deployment-final-r4')) {
        throw "$service did not prove deployment-final-r4 in retained deployment logs."
    }
    $blockerMatches = Invoke-RailwayCapture -Arguments @(
        "logs", "-s", $service, "-e", $Environment, "--since", $hoursToken,
        "--lines", "50", "--filter", $blockerFilter
    )
    if (-not [string]::IsNullOrWhiteSpace($blockerMatches)) {
        throw "$service soak logs contain a blocking pattern; inspect the filtered Railway output."
    }
    foreach ($pattern in $forbidden) {
        if ($logs -match $pattern) {
            throw "$service soak log tail contains blocking pattern: $pattern"
        }
    }
    $serviceEvidence[$service] = @{
        log_path = $logPath
        alembic_head_proven = $true
        patch_proven = $true
        blocker_scan = "PASS"
    }
}

$metrics = Invoke-RailwayCapture -Arguments @(
    "metrics", "--all", "-e", $Environment,
    "--since", $hoursToken, "--json"
)
$metricsPath = Join-Path $evidenceDir "railway_metrics.json"
Set-Content -Path $metricsPath -Value $metrics -Encoding UTF8

$statusLower = $status.ToLowerInvariant()
foreach ($service in $services) {
    if (-not $statusLower.Contains($service.ToLowerInvariant())) {
        throw "Railway service status did not include $service."
    }
}
if ($statusLower -match '"status"\s*:\s*"(crashed|failed|removed)"') {
    throw "At least one Railway service is not healthy after the soak window."
}

$summary = [ordered]@{
    evidence_type = "staging_soak_certification"
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    environment = $Environment
    requested_window_hours = $Hours
    status = "PASS"
    services = $serviceEvidence
    metrics_path = $metricsPath
    service_status_path = $statusPath
    note = "PASS certifies blocker-free Railway logs/status over the requested lookback. It does not independently prove trading profitability, provider SLAs, payments, email, legal approval, or backup/restore success."
}
$summaryPath = Join-Path $evidenceDir "staging_soak_summary.json"
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $summaryPath -Encoding UTF8
Write-Host "Staging soak certification PASS: $summaryPath" -ForegroundColor Green
