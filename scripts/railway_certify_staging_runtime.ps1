[CmdletBinding()]
param(
    [string]$Environment = "staging",
    [string]$DatabaseService = "Postgres-R8Lr",
    [string]$WorkerService = "SignalRankAI",
    [string]$EngineService = "striking-optimism",
    [string]$FrontdoorService = "bountiful-miracle",
    [int]$WindowHours = 6,
    [switch]$RequirePayment,
    [switch]$RequireEmail
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Railway {
    param([Parameter(Mandatory=$true)][string[]]$Arguments,[switch]$Capture)
    Write-Host ("railway " + ($Arguments -join " ")) -ForegroundColor DarkGray
    if ($Capture) {
        $output = & railway @Arguments 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { throw "Railway command failed ($LASTEXITCODE): railway $($Arguments -join ' ')`n$output" }
        return $output
    }
    & railway @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Railway command failed ($LASTEXITCODE): railway $($Arguments -join ' ')" }
}

function Get-VariableValue {
    param([object]$Node,[string]$Name)
    if ($null -eq $Node) { return $null }
    if ($Node -is [System.Management.Automation.PSCustomObject]) {
        $direct = $Node.PSObject.Properties[$Name]
        if ($null -ne $direct -and $null -ne $direct.Value) { return [string]$direct.Value }
        $nameProp = $Node.PSObject.Properties["name"]
        $valueProp = $Node.PSObject.Properties["value"]
        if ($null -ne $nameProp -and $null -ne $valueProp -and [string]$nameProp.Value -eq $Name) { return [string]$valueProp.Value }
        foreach ($property in $Node.PSObject.Properties) {
            $found = Get-VariableValue -Node $property.Value -Name $Name
            if ($found) { return $found }
        }
    } elseif ($Node -is [System.Collections.IEnumerable] -and $Node -isnot [string]) {
        foreach ($item in $Node) {
            $found = Get-VariableValue -Node $item -Name $Name
            if ($found) { return $found }
        }
    }
    return $null
}

function Invoke-WithEnv {
    param([hashtable]$Values,[scriptblock]$Action)
    $previous = @{}
    foreach ($key in $Values.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key,"Process")
        [Environment]::SetEnvironmentVariable($key,[string]$Values[$key],"Process")
    }
    try { & $Action }
    finally {
        foreach ($key in $Values.Keys) { [Environment]::SetEnvironmentVariable($key,$previous[$key],"Process") }
    }
}

if ($Environment.ToLowerInvariant() -in @("production","prod")) { throw "This command is staging-only." }
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) { throw "Railway CLI is not installed." }
if (-not (Test-Path "scripts/staging_runtime_proof.py")) { throw "Run from the SignalRankAI project root." }

Invoke-Railway -Arguments @("whoami")
Invoke-Railway -Arguments @("environment",$Environment)
$dbRaw = Invoke-Railway -Arguments @("variable","list","-s",$DatabaseService,"-e",$Environment,"--json") -Capture
$dbVariables = $dbRaw | ConvertFrom-Json
$publicDb = Get-VariableValue -Node $dbVariables -Name "DATABASE_PUBLIC_URL"
if (-not $publicDb) { $publicDb = Get-VariableValue -Node $dbVariables -Name "POSTGRES_PUBLIC_URL" }
if (-not $publicDb) { throw "No public PostgreSQL URL is available for read-only certification." }
if ($publicDb -match '(?i)\.railway\.internal') { throw "Certification URL resolved to a Railway private hostname; enable/tunnel the DB public endpoint." }

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$evidence = Join-Path (Get-Location) "deployment_evidence\runtime-$timestamp"
New-Item -ItemType Directory -Path $evidence -Force | Out-Null

$envValues = @{
    "DATABASE_URL" = $publicDb
    "DATABASE_MIGRATION_URL" = $publicDb
    "RAILWAY_ENVIRONMENT_NAME" = $Environment
    "APP_ENV" = $Environment
    "ENVIRONMENT" = $Environment
}
$proofPath = Join-Path $evidence "runtime_proof.json"
$proofArguments = @("scripts/staging_runtime_proof.py","--window-hours",[string]$WindowHours,"--require-runtime","--output",$proofPath)
if ($RequirePayment) { $proofArguments += "--require-payment" }
if ($RequireEmail) { $proofArguments += "--require-email" }
Invoke-WithEnv -Values $envValues -Action {
    & python @proofArguments
    if ($LASTEXITCODE -ne 0) { throw "Runtime proof is not complete. See $proofPath" }
}

$blockingPatterns = @(
    'schema_gate.*BLOCKED',
    'Database schema admission failed',
    'UndefinedTableError',
    'UndefinedColumnError',
    'AmbiguousParameterError',
    'relation ".*" does not exist',
    'column .* does not exist'
)
foreach ($service in @($WorkerService,$EngineService,$FrontdoorService)) {
    $logs = Invoke-Railway -Arguments @("logs","-s",$service,"-e",$Environment,"--latest","--lines","2000") -Capture
    Set-Content -Path (Join-Path $evidence (($service -replace '[^A-Za-z0-9_.-]','_') + '.log')) -Value $logs -Encoding UTF8
    if (-not $logs.Contains('alembic_current=0038_account_security_product')) { throw "$service does not prove Alembic 0038 in latest logs." }
    if (-not $logs.Contains('patch=deployment-final-r4')) { throw "$service is not running deployment-final-r4." }
    foreach ($pattern in $blockingPatterns) {
        if ($logs -match $pattern) { throw "$service contains blocking log pattern: $pattern" }
    }
}

$status = Invoke-Railway -Arguments @("service","status","-a","--json") -Capture
Set-Content -Path (Join-Path $evidence "service_status.json") -Value $status -Encoding UTF8
$metrics = Invoke-Railway -Arguments @("metrics","--all","-e",$Environment,"--since","1h","--json") -Capture
Set-Content -Path (Join-Path $evidence "metrics_1h.json") -Value $metrics -Encoding UTF8

$summary = [ordered]@{
    status = "PASS"
    environment = $Environment
    window_hours = $WindowHours
    require_payment = [bool]$RequirePayment
    require_email = [bool]$RequireEmail
    evidence_directory = $evidence
    generated_at = (Get-Date).ToString("o")
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $evidence "runtime_certification_summary.json") -Encoding UTF8
Write-Host "Runtime staging certification PASS." -ForegroundColor Green
Write-Host "Evidence: $evidence" -ForegroundColor Green
