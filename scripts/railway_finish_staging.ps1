[CmdletBinding()]
param(
    [string]$Environment = "staging",
    [string]$WorkerService = "SignalRankAI",
    [string]$EngineService = "striking-optimism",
    [string]$FrontdoorService = "bountiful-miracle",
    [string]$DatabaseService = "",
    [int]$DiscoveryTop = 100,
    [switch]$AcknowledgeStagingMigration,
    [switch]$SkipCodeUpload
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Railway {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Capture
    )
    Write-Host ("railway " + ($Arguments -join " ")) -ForegroundColor DarkGray
    if ($Capture) {
        $output = & railway @Arguments 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            throw "Railway command failed ($LASTEXITCODE): railway $($Arguments -join ' ')`n$output"
        }
        return $output
    }
    & railway @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Railway command failed ($LASTEXITCODE): railway $($Arguments -join ' ')"
    }
}

function Get-ObjectNames {
    param([object]$Value)
    $results = New-Object System.Collections.Generic.List[string]
    function Walk([object]$Node) {
        if ($null -eq $Node) { return }
        if ($Node -is [string] -or $Node -is [ValueType]) { return }
        if ($Node -is [System.Collections.IEnumerable] -and $Node -isnot [System.Management.Automation.PSCustomObject]) {
            foreach ($item in $Node) { Walk $item }
            return
        }
        foreach ($property in $Node.PSObject.Properties) {
            if ($property.Name -eq "name" -and $property.Value -is [string]) {
                $results.Add([string]$property.Value)
            }
            Walk $property.Value
        }
    }
    Walk $Value
    return $results | Sort-Object -Unique
}

function Set-ServiceVariables {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string[]]$Pairs
    )
    $args = @("variable", "set", "-s", $Service, "-e", $Environment, "--skip-deploys") + $Pairs
    Invoke-Railway -Arguments $args
}

function Get-LatestDeploymentStatus {
    param([Parameter(Mandatory = $true)][string]$Service)
    $raw = Invoke-Railway -Arguments @(
        "deployment", "list", "-s", $Service, "-e", $Environment,
        "--limit", "1", "--json"
    ) -Capture
    $parsed = $raw | ConvertFrom-Json
    if ($parsed -is [System.Array]) {
        if ($parsed.Count -eq 0) { return "UNKNOWN" }
        return [string]$parsed[0].status
    }
    if ($parsed.PSObject.Properties.Name -contains "deployments") {
        if ($parsed.deployments.Count -eq 0) { return "UNKNOWN" }
        return [string]$parsed.deployments[0].status
    }
    if ($parsed.PSObject.Properties.Name -contains "status") {
        return [string]$parsed.status
    }
    return "UNKNOWN"
}

function Wait-Deployment {
    param([Parameter(Mandatory = $true)][string]$Service)
    $terminalSuccess = @("SUCCESS")
    $terminalFailure = @("FAILED", "CRASHED", "REMOVED")
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Seconds 10
        $status = (Get-LatestDeploymentStatus -Service $Service).ToUpperInvariant()
        Write-Host "[$Service] deployment status=$status"
        if ($terminalSuccess -contains $status) { return }
        if ($terminalFailure -contains $status) {
            throw "$Service deployment ended with status $status"
        }
    }
    throw "$Service deployment did not reach a terminal status"
}

function Get-DatabaseIdentity {
    param([Parameter(Mandatory = $true)][string]$Service)
    $raw = Invoke-Railway -Arguments @(
        "run", "--no-local", "-s", $Service, "-e", $Environment,
        "python", "scripts/database_identity.py",
        "--expect-head", "0038_account_security_product"
    ) -Capture
    $matches = [regex]::Matches($raw, '(?m)^\{.*"fingerprint".*\}$')
    if ($matches.Count -eq 0) {
        throw "Could not parse database identity for $Service.`n$raw"
    }
    return ($matches[$matches.Count - 1].Value | ConvertFrom-Json)
}

function Test-ServiceLogs {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$EvidenceDirectory
    )
    $logs = Invoke-Railway -Arguments @(
        "logs", "-s", $Service, "-e", $Environment,
        "--latest", "--lines", "2000"
    ) -Capture
    $path = Join-Path $EvidenceDirectory ((($Service -replace '[^A-Za-z0-9_.-]', '_')) + ".log")
    Set-Content -Path $path -Value $logs -Encoding UTF8

    $forbidden = @(
        'alembic_current=0034_production_integrity',
        'UndefinedTableError',
        'UndefinedColumnError',
        'relation "subscription_products" does not exist',
        'relation "instruments" does not exist',
        'relation "webhook_deliveries" does not exist',
        'column users.public_user_id does not exist'
    )
    foreach ($needle in $forbidden) {
        if ($logs.Contains($needle)) {
            throw "$Service still contains a blocking post-deploy log pattern: $needle"
        }
    }
    if (-not $logs.Contains('alembic_current=0038_account_security_product')) {
        throw "$Service did not prove alembic_current=0038_account_security_product in its latest logs"
    }
}

if ($Environment.ToLowerInvariant() -in @("production", "prod")) {
    throw "This script is staging-only. Production requires backup-gated scripts/controlled_migrate.py."
}
if (-not $AcknowledgeStagingMigration) {
    throw "Re-run with -AcknowledgeStagingMigration to authorize the staging schema upgrade."
}
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    throw "Railway CLI is not installed or not available in PATH."
}
if (-not (Test-Path "alembic.ini") -or -not (Test-Path "scripts/staging_migrate_and_bootstrap.py")) {
    throw "Run this script from the extracted SignalRankAI project root."
}

Invoke-Railway -Arguments @("whoami")
Invoke-Railway -Arguments @("environment", $Environment)
$statusJson = Invoke-Railway -Arguments @("service", "list", "--json") -Capture
$statusObject = $statusJson | ConvertFrom-Json
$serviceNames = @(Get-ObjectNames -Value $statusObject)

foreach ($required in @($WorkerService, $EngineService, $FrontdoorService)) {
    if ($serviceNames -notcontains $required) {
        throw "Required service '$required' was not found. Available names: $($serviceNames -join ', ')"
    }
}

if (-not $DatabaseService) {
    $DatabaseService = $serviceNames |
        Where-Object { $_ -match '(?i)postgres|postgresql' } |
        Select-Object -First 1
}
if (-not $DatabaseService) {
    throw "Could not auto-detect the PostgreSQL service. Pass -DatabaseService with its exact Railway name."
}
Write-Host "Using PostgreSQL service: $DatabaseService" -ForegroundColor Cyan

$dbReference = '${{' + $DatabaseService + '.DATABASE_URL}}'
$services = @($WorkerService, $EngineService, $FrontdoorService)
$commonVariables = @(
    "DATABASE_URL=$dbReference",
    "APP_VERSION=1.5.1",
    "EXPECTED_ALEMBIC_HEAD=0038_account_security_product",
    "DATABASE_SCHEMA_GATE_ENABLED=1",
    "SIGNALRANK_ENV_PROFILE=staging-certification",
    "ALLOW_STATIC_ASSET_FALLBACK=0",
    "DYNAMIC_UNIVERSE_ENABLED=1",
    "DYNAMIC_INSTRUMENT_DISCOVERY_ENABLED=1",
    "REAL_EXECUTION_ENABLED=0",
    "AUTO_EXECUTION_ENABLED=0",
    "AUTO_TRADE_ENABLED=0",
    "COPY_TRADE_ENABLED=0",
    "BYBIT_EXECUTION_ENABLED=0",
    "HYPERLIQUID_MAINNET_EXECUTION_ENABLED=0",
    "REAL_PAYOUTS_ENABLED=0",
    "PAYSTACK_TRANSFERS_ENABLED=0",
    "PAYMENTS_PUBLIC_ENABLED=0"
)
foreach ($service in $services) {
    Set-ServiceVariables -Service $service -Pairs $commonVariables
}
Set-ServiceVariables -Service $FrontdoorService -Pairs @(
    "DATABASE_MIGRATION_URL=$dbReference",
    "STAGING_MIGRATION_ACKNOWLEDGED=1",
    "BOOTSTRAP_DISCOVER=1",
    "BOOTSTRAP_DISCOVERY_TOP=$DiscoveryTop"
)

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$evidenceDirectory = Join-Path (Get-Location) "deployment_evidence\$timestamp"
New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null

Write-Host "Applying the one-owner migration and ecosystem bootstrap..." -ForegroundColor Cyan
Invoke-Railway -Arguments @(
    "run", "--no-local", "-s", $FrontdoorService, "-e", $Environment,
    "python", "scripts/staging_migrate_and_bootstrap.py",
    "--discover", "--top", [string]$DiscoveryTop,
    "--skip-certification",
    "--output", (Join-Path $evidenceDirectory "staging_migration_evidence.json")
)

$identities = @{}
foreach ($service in $services) {
    $identity = Get-DatabaseIdentity -Service $service
    if (-not $identity.ok) {
        throw "$service is not at the expected Alembic head."
    }
    $identities[$service] = $identity
}
$fingerprints = @($identities.Values | ForEach-Object { $_.fingerprint } | Sort-Object -Unique)
$identities | ConvertTo-Json -Depth 8 | Set-Content `
    -Path (Join-Path $evidenceDirectory "database_identities.json") -Encoding UTF8
if ($fingerprints.Count -ne 1) {
    throw "Services do not resolve to one PostgreSQL database. Fingerprints: $($fingerprints -join ', ')"
}
Write-Host "All services resolve to one migrated PostgreSQL database." -ForegroundColor Green

if (-not $SkipCodeUpload) {
    foreach ($service in @($WorkerService, $EngineService, $FrontdoorService)) {
        Write-Host "Uploading and deploying the patched source to $service..." -ForegroundColor Cyan
        Invoke-Railway -Arguments @("up", "-s", $service, "-e", $Environment, "--detach")
        Wait-Deployment -Service $service
    }
} else {
    foreach ($service in @($WorkerService, $EngineService, $FrontdoorService)) {
        Invoke-Railway -Arguments @("redeploy", "-s", $service, "-e", $Environment, "-y")
        Wait-Deployment -Service $service
    }
}

foreach ($service in $services) {
    Test-ServiceLogs -Service $service -EvidenceDirectory $evidenceDirectory
}

Write-Host "Running post-deployment staging certification..." -ForegroundColor Cyan
$certificationArguments = @(
    "run", "--no-local", "-s", $FrontdoorService, "-e", $Environment,
    "python", "-m", "tools.staging_certification"
)
Write-Host ("railway " + ($certificationArguments -join " ")) -ForegroundColor DarkGray
$certificationOutput = & railway @certificationArguments 2>&1 | Out-String
$certificationExitCode = $LASTEXITCODE
Set-Content -Path (Join-Path $evidenceDirectory "staging_certification.log") `
    -Value $certificationOutput -Encoding UTF8

$summary = [ordered]@{
    status = "PASS"
    environment = $Environment
    database_service = $DatabaseService
    database_fingerprint = $fingerprints[0]
    alembic_head = "0038_account_security_product"
    certification_exit_code = $certificationExitCode
    certification_status = $(if ($certificationExitCode -eq 0) { "PASS" } else { "PENDING_RUNTIME_EVIDENCE" })
    services = $services
    evidence_directory = $evidenceDirectory
    generated_at = (Get-Date).ToString("o")
    note = "Infrastructure/schema deployment completed. Fresh-signal, paper-position, payment and soak evidence remain runtime observations."
}
$summary | ConvertTo-Json -Depth 8 | Set-Content `
    -Path (Join-Path $evidenceDirectory "deployment_summary.json") -Encoding UTF8

Write-Host "Staging schema and service deployment completed successfully." -ForegroundColor Green
Write-Host "Evidence: $evidenceDirectory" -ForegroundColor Green
