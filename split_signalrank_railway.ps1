[CmdletBinding()]
param(
    [string]$Environment = "staging",
    [string]$SourceService = "SignalRankAI",
    [string]$EngineService = "SignalRankAI-engine",
    [string]$WorkerService = "SignalRankAI-worker",
    [string]$Region = "",
    [switch]$SkipVariableCopy,
    [switch]$SkipDeploy,
    [switch]$KeepRailwayJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Railway {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Capture
    )

    Write-Host ("railway " + ($Arguments -join " ")) -ForegroundColor DarkGray
    if ($Capture) {
        $output = & railway @Arguments 2>&1
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

function Assert-Prerequisites {
    if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
        throw "Railway CLI is not installed or is not on PATH. Install it, then run 'railway login'."
    }
    if (-not (Test-Path "./start.sh")) {
        throw "Run this script from the SignalRankAI repository root; start.sh was not found."
    }
    if (-not (Test-Path "./main.py")) {
        throw "Run this script from the SignalRankAI repository root; main.py was not found."
    }
    if (-not (Test-Path "./runtime/roles.py")) {
        throw "This build does not contain the decomposed runtime role contract (runtime/roles.py)."
    }

    Invoke-Railway -Arguments @("whoami") | Out-Null
    Invoke-Railway -Arguments @("service", "status", "--service", $SourceService, "--environment", $Environment, "--json") -Capture | Out-Null
}

function Test-ServiceExists {
    param([Parameter(Mandatory = $true)][string]$Name)
    & railway service status --service $Name --environment $Environment --json *> $null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Service {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (Test-ServiceExists -Name $Name) {
        Write-Host "Service already exists: $Name" -ForegroundColor Yellow
        return
    }

    Invoke-Railway -Arguments @("add", "--service", $Name, "--json") | Out-Null
}

function Get-CopyableVariables {
    $lines = Invoke-Railway -Arguments @(
        "variable", "list",
        "--service", $SourceService,
        "--environment", $Environment,
        "--kv"
    ) -Capture

    $excluded = @{
        "RUN_MODE" = $true
        "SERVICE_ROLE" = $true
        "HONOR_RUN_MODE_ON_RAILWAY" = $true
        "RUN_ENGINE_LOOP" = $true
        "RUN_WORKER_LOOP" = $true
        "SCHEDULER_OWNER" = $true
        "DB_ROLE" = $true
        "DB_APP_NAME" = $true
        "DB_POOL_SIZE" = $true
        "DB_MAX_OVERFLOW" = $true
        "DB_POOL_RAILWAY_ABSOLUTE_CAP" = $true
        "DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP" = $true
        "DB_MAX_CONCURRENT_SESSIONS" = $true
        "DB_FOREGROUND_RESERVED_SESSIONS" = $true
        "DB_INTERACTIVE_MAX_CONCURRENT_SESSIONS" = $true
        "DB_CRITICAL_MAX_CONCURRENT_SESSIONS" = $true
        "DB_BACKGROUND_MAX_CONCURRENT_SESSIONS" = $true
        "DB_ALLOW_REVIEWED_MONOLITH_POOL" = $true
        "STARTUP_OPS_ENABLED" = $true
        "STARTUP_DATA_SELFCHECK_ENABLED" = $true
        "DECOMPOSED_TOPOLOGY_ENABLED" = $true
        "RAILWAY_SERVICE_NAME" = $true
        "RAILWAY_SERVICE_ID" = $true
        "RAILWAY_REPLICA_ID" = $true
        "RAILWAY_DEPLOYMENT_ID" = $true
        "PORT" = $true
    }

    $pairs = New-Object System.Collections.Generic.List[string]
    foreach ($lineObject in $lines) {
        $line = [string]$lineObject
        if ([string]::IsNullOrWhiteSpace($line) -or -not $line.Contains("=")) {
            continue
        }

        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1]
        if ([string]::IsNullOrWhiteSpace($key)) {
            continue
        }
        if ($key.StartsWith("RAILWAY_", [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        if ($excluded.ContainsKey($key)) {
            continue
        }

        $pairs.Add("$key=$value")
    }
    return $pairs.ToArray()
}

function Set-VariablesBatched {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string[]]$Pairs
    )

    $batchSize = 20
    for ($offset = 0; $offset -lt $Pairs.Count; $offset += $batchSize) {
        $last = [Math]::Min($offset + $batchSize - 1, $Pairs.Count - 1)
        $batch = $Pairs[$offset..$last]
        $args = @(
            "variable", "set",
            "--service", $Service,
            "--environment", $Environment,
            "--skip-deploys"
        ) + $batch
        Invoke-Railway -Arguments $args | Out-Null
    }
}

function Set-ServiceVariables {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][hashtable]$Variables
    )

    $pairs = @()
    foreach ($entry in $Variables.GetEnumerator()) {
        $pairs += "$($entry.Key)=$($entry.Value)"
    }
    Set-VariablesBatched -Service $Service -Pairs $pairs
}

function Set-ServiceConfig {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Message
    )

    Invoke-Railway -Arguments @(
        "environment", "edit",
        "--environment", $Environment,
        "--service-config", $Service, $Path, $Value,
        "--message", $Message
    ) | Out-Null
}

function Prepare-NeutralRailwayConfig {
    if ($KeepRailwayJson) {
        Write-Host "Keeping the existing railway.json. Ensure it does not force /readyz or pre-deploy migrations on non-HTTP roles." -ForegroundColor Yellow
        return
    }

    $path = Join-Path (Get-Location) "railway.json"
    if (Test-Path $path) {
        $backup = Join-Path (Get-Location) "railway.monolith.backup.json"
        Copy-Item $path $backup -Force
        Write-Host "Backed up railway.json to railway.monolith.backup.json" -ForegroundColor Yellow
    }

    $config = [ordered]@{
        '$schema' = "https://railway.com/railway.schema.json"
        build = [ordered]@{
            builder = "NIXPACKS"
        }
        deploy = [ordered]@{
            startCommand = "bash start.sh"
            restartPolicyType = "ON_FAILURE"
            restartPolicyMaxRetries = 5
        }
    }

    $config | ConvertTo-Json -Depth 8 | Set-Content -Path $path -Encoding UTF8
    Write-Host "Wrote a neutral multi-service railway.json." -ForegroundColor Green
    Write-Host "Commit this railway.json after validating staging, otherwise future GitHub auto-deploys may restore monolith-only settings." -ForegroundColor Yellow
}

function Deploy-Service {
    param([Parameter(Mandatory = $true)][string]$Service)
    if ($SkipDeploy) {
        Write-Host "Skipping deployment for $Service" -ForegroundColor Yellow
        return
    }

    Invoke-Railway -Arguments @(
        "up",
        "--service", $Service,
        "--environment", $Environment
    )
}

function Set-OneReplicaIfRequested {
    param([Parameter(Mandatory = $true)][string]$Service)
    if ([string]::IsNullOrWhiteSpace($Region)) {
        return
    }
    Invoke-Railway -Arguments @(
        "scale",
        "--service", $Service,
        "--environment", $Environment,
        "$Region=1"
    ) | Out-Null
}

Assert-Prerequisites
Prepare-NeutralRailwayConfig

Ensure-Service -Name $EngineService
Ensure-Service -Name $WorkerService

if (-not $SkipVariableCopy) {
    Write-Host "Copying shared variables from $SourceService..." -ForegroundColor Cyan
    $sharedPairs = Get-CopyableVariables
    if ($sharedPairs.Count -gt 0) {
        Set-VariablesBatched -Service $EngineService -Pairs $sharedPairs
        Set-VariablesBatched -Service $WorkerService -Pairs $sharedPairs
    }
}

# Front door: Telegram webhook + command handling + existing bot scheduler.
# Engine and legacy worker loops are explicitly moved out.
Set-ServiceVariables -Service $SourceService -Variables @{
    RUN_MODE = "frontdoor"
    APP_VERSION = "1.3.6"
    APP_ENV = $Environment
    SERVICE_ROLE = "frontdoor"
    DB_ROLE = "frontdoor"
    DB_APP_NAME = "signalrankai/frontdoor"
    HONOR_RUN_MODE_ON_RAILWAY = "true"
    DECOMPOSED_TOPOLOGY_ENABLED = "1"
    RUN_ENGINE_LOOP = "0"
    RUN_WORKER_LOOP = "0"
    SCHEDULER_OWNER = "monolith"
    STARTUP_OPS_ENABLED = "0"
    STARTUP_DATA_SELFCHECK_ENABLED = "0"
    DEPLOYMENT_DIAGNOSTICS_ENABLED = "0"
    ACTIVE_SIGNAL_KEYBOARD_REFRESH_ENABLED = "0"
    TELEGRAM_ACTIVE_KEYBOARD_REFRESH_ENABLED = "0"
    BOT_COMMAND_SCOPE_BULK_REFRESH_ENABLED = "0"
    DB_ALLOW_REVIEWED_MONOLITH_POOL = "0"
    DB_POOL_SIZE = "5"
    DB_MAX_OVERFLOW = "1"
    DB_POOL_RAILWAY_ABSOLUTE_CAP = "5"
    DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP = "1"
    DB_MAX_CONCURRENT_SESSIONS = "6"
    DB_FOREGROUND_RESERVED_SESSIONS = "4"
    DB_INTERACTIVE_MAX_CONCURRENT_SESSIONS = "3"
    DB_CRITICAL_MAX_CONCURRENT_SESSIONS = "2"
    DB_BACKGROUND_MAX_CONCURRENT_SESSIONS = "1"
    OUTCOME_NOTIFICATION_INTERVAL_SECONDS = "60"
    MONITOR_REFRESH_INTERVAL_SECONDS = "120"
}

# Dedicated signal engine singleton.
Set-ServiceVariables -Service $EngineService -Variables @{
    RUN_MODE = "engine"
    APP_VERSION = "1.3.6"
    APP_ENV = $Environment
    SERVICE_ROLE = "engine"
    DB_ROLE = "engine"
    DB_APP_NAME = "signalrankai/engine"
    HONOR_RUN_MODE_ON_RAILWAY = "true"
    DECOMPOSED_TOPOLOGY_ENABLED = "1"
    RUN_DB_MIGRATIONS_AT_BOOT = "false"
    AUTO_MIGRATE = "false"
    STARTUP_OPS_ENABLED = "0"
    STARTUP_DATA_SELFCHECK_ENABLED = "1"
    DEPLOYMENT_DIAGNOSTICS_ENABLED = "0"
    DB_ALLOW_REVIEWED_MONOLITH_POOL = "0"
    DB_POOL_SIZE = "4"
    DB_MAX_OVERFLOW = "1"
    DB_POOL_RAILWAY_ABSOLUTE_CAP = "4"
    DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP = "1"
    DB_MAX_CONCURRENT_SESSIONS = "5"
    DB_FOREGROUND_RESERVED_SESSIONS = "2"
    DB_INTERACTIVE_MAX_CONCURRENT_SESSIONS = "1"
    DB_CRITICAL_MAX_CONCURRENT_SESSIONS = "2"
    DB_BACKGROUND_MAX_CONCURRENT_SESSIONS = "2"
    WORKER_ENGINE_PULSE_ENABLED = "0"
}

# Dedicated legacy background worker. It preserves outcome tracking, shadow
# tracking, candle capture, paper trading, retries and Engine Pulse together.
Set-ServiceVariables -Service $WorkerService -Variables @{
    RUN_MODE = "worker"
    APP_VERSION = "1.3.6"
    APP_ENV = $Environment
    SERVICE_ROLE = "worker"
    DB_ROLE = "worker"
    DB_APP_NAME = "signalrankai/worker"
    HONOR_RUN_MODE_ON_RAILWAY = "true"
    DECOMPOSED_TOPOLOGY_ENABLED = "1"
    RUN_DB_MIGRATIONS_AT_BOOT = "false"
    AUTO_MIGRATE = "false"
    STARTUP_OPS_ENABLED = "0"
    STARTUP_DATA_SELFCHECK_ENABLED = "0"
    DEPLOYMENT_DIAGNOSTICS_ENABLED = "0"
    DB_ALLOW_REVIEWED_MONOLITH_POOL = "0"
    DB_POOL_SIZE = "6"
    DB_MAX_OVERFLOW = "2"
    DB_POOL_RAILWAY_ABSOLUTE_CAP = "6"
    DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP = "2"
    DB_MAX_CONCURRENT_SESSIONS = "8"
    DB_FOREGROUND_RESERVED_SESSIONS = "2"
    DB_INTERACTIVE_MAX_CONCURRENT_SESSIONS = "1"
    DB_CRITICAL_MAX_CONCURRENT_SESSIONS = "2"
    DB_BACKGROUND_MAX_CONCURRENT_SESSIONS = "5"
    WORKER_ENGINE_PULSE_ENABLED = "1"
    ENGINE_PULSE_INTERVAL_SECONDS = "86400"
    ENGINE_PULSE_WINDOW_HOURS = "24"
    ENGINE_PULSE_LOCK_KEY = "signalrank:admin_pulse:daily"
    ENGINE_PULSE_LOCK_TTL_SECONDS = "86370"
}

$preDeploy = "python scripts/controlled_migrate.py --output /tmp/signalrank_migration_evidence.json && python scripts/deployment_diagnostics.py --phase predeploy --profile production-advisory --strict-core --output /tmp/signalrank_predeploy_diagnostics.json"

Set-ServiceConfig -Service $SourceService -Path "startCommand" -Value "bash start.sh" -Message "Configure SignalRankAI front door"
Set-ServiceConfig -Service $SourceService -Path "healthcheckPath" -Value "/readyz" -Message "Configure front-door readiness"
Set-ServiceConfig -Service $SourceService -Path "healthcheckTimeout" -Value "300" -Message "Configure front-door healthcheck timeout"
Set-ServiceConfig -Service $SourceService -Path "preDeployCommand" -Value $preDeploy -Message "Assign migrations to front door"

Set-ServiceConfig -Service $EngineService -Path "startCommand" -Value "bash start.sh" -Message "Configure engine role"
Set-ServiceConfig -Service $WorkerService -Path "startCommand" -Value "bash start.sh" -Message "Configure worker role"

Set-OneReplicaIfRequested -Service $SourceService
Set-OneReplicaIfRequested -Service $EngineService
Set-OneReplicaIfRequested -Service $WorkerService

Write-Host "Deploying the front door first, so the old embedded engine/worker stop before dedicated roles start." -ForegroundColor Cyan
Deploy-Service -Service $SourceService
Deploy-Service -Service $EngineService
Deploy-Service -Service $WorkerService

Write-Host "" 
Write-Host "Railway service status:" -ForegroundColor Cyan
Invoke-Railway -Arguments @("service", "status", "--all", "--environment", $Environment)

Write-Host "" 
Write-Host "Validation commands:" -ForegroundColor Green
Write-Host "railway logs --service $SourceService --environment $Environment --latest --lines 250"
Write-Host "railway logs --service $EngineService --environment $Environment --latest --lines 250"
Write-Host "railway logs --service $WorkerService --environment $Environment --latest --lines 250"
Write-Host ""
Write-Host "Expected ownership:" -ForegroundColor Green
Write-Host "  $SourceService : run_mode=frontdoor; webhook/bot/scheduler only; engine=false; worker=false"
Write-Host "  $EngineService : run_mode=engine only"
Write-Host "  $WorkerService : boot may report run_mode=delivery (worker alias); outcome/shadow/candles/paper/Engine Pulse"
Write-Host ""
Write-Host "Do not scale $SourceService above one replica yet. The current Telegram bot scheduler and command processing are not fully decomposed." -ForegroundColor Yellow
