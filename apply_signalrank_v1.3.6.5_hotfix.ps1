param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectPath = (Resolve-Path $ProjectRoot).Path
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $projectPath ".signalrank-backups\v1.3.6.5-$timestamp"

$manifestPath = Join-Path $sourceRoot "v1.3.6.5-overlay-manifest.txt"
if (-not (Test-Path $manifestPath)) {
    throw "Overlay manifest not found: $manifestPath"
}

$files = Get-Content $manifestPath | Where-Object {
    $_ -and -not $_.Trim().StartsWith("#")
}

foreach ($relative in $files) {
    $source = Join-Path $sourceRoot $relative
    if (-not (Test-Path $source)) {
        throw "Overlay source file is missing: $relative"
    }

    $destination = Join-Path $projectPath $relative
    if (Test-Path $destination) {
        $backup = Join-Path $backupRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
        Copy-Item $destination $backup -Force
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item $source $destination -Force
}

Write-Host "Applied SignalRankAI v1.3.6.5 overlay."
Write-Host "Backup directory: $backupRoot"

Push-Location $projectPath
try {
    python -m compileall -q core data db engine ml services signalrank_telegram worker scripts tests railway_main.py
    if ($LASTEXITCODE -ne 0) {
        throw "Python compilation failed after overlay application. Restore from $backupRoot"
    }

    python scripts/verify_v1365_production_integrity.py
    if ($LASTEXITCODE -ne 0) {
        throw "v1.3.6.5 integrity verification failed. Restore from $backupRoot"
    }
}
finally {
    Pop-Location
}

Write-Host "Compilation and production-integrity verification passed."
