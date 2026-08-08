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
    'schema_gate.*BLOCKED',
    'Database schema admission failed',
    'UndefinedTableError',
    'UndefinedColumnError',
    'AmbiguousParameterError',
    'relation .* does not exist',
    'column .* does not exist',
    'task crashed:',
    '\[FATAL\]',
    'OutOfMemory',
    'Killed process'
)

$serviceEvidence = @{}
foreach ($service in $services) {
    $safeName = $service -replace '[^A-Za-z0-9_.-]', '_'
    $logs = Invoke-RailwayCapture -Arguments @(
        "logs", "-s", $service, "-e", $Environment,
        "--since", $hoursToken, "--lines", "10000"
    )
    $logPath = Join-Path $evidenceDir ("$safeName-soak.log")
    Set-Content -Path $logPath -Value $logs -Encoding UTF8

    if (-not $logs.Contains('alembic_current=0038_account_security_product')) {
        throw "$service did not prove Alembic head 0038 within the soak window."
    }
    if (-not $logs.Contains('patch=deployment-final-r4')) {
        throw "$service did not prove deployment-final-r4 within the soak window."
    }
    foreach ($pattern in $forbidden) {
        if ($logs -match $pattern) {
            throw "$service soak logs contain blocking pattern: $pattern"
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

$status = Invoke-RailwayCapture -Arguments @("service", "status", "-a", "--json")
$statusPath = Join-Path $evidenceDir "railway_service_status.json"
Set-Content -Path $statusPath -Value $status -Encoding UTF8
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
