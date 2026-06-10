param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host $Message
}

function Invoke-Step {
    param(
        [scriptblock]$Action,
        [string]$Description
    )

    if ($DryRun) {
        Write-Step "[dry-run] $Description"
    }
    else {
        & $Action
    }
}

function Test-SameFile {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        return $false
    }

    $sourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
    $destHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
    return $sourceHash -eq $destHash
}

function Backup-IfChanged {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        return
    }

    if (Test-SameFile -Source $Source -Destination $Destination) {
        return
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupPath = "$Destination.bak.$stamp"
    Invoke-Step -Description "Copy-Item '$Destination' '$backupPath'" -Action {
        Copy-Item -LiteralPath $Destination -Destination $backupPath -Force
    }
}

function Install-File {
    param(
        [string]$Source,
        [string]$Destination
    )

    $destDir = Split-Path -Parent $Destination
    Invoke-Step -Description "New-Item -ItemType Directory '$destDir'" -Action {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    if (Test-SameFile -Source $Source -Destination $Destination) {
        Write-Step "Skip unchanged: $Destination"
        return
    }

    Backup-IfChanged -Source $Source -Destination $Destination
    Invoke-Step -Description "Copy-Item '$Source' '$Destination'" -Action {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
    Write-Step "Installed: $Destination"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentsSource = Join-Path $scriptDir "AGENTS.md"
$scriptsSource = Join-Path $scriptDir "scripts"

if (-not (Test-Path -LiteralPath $agentsSource -PathType Leaf)) {
    throw "Missing $agentsSource"
}

if (-not (Test-Path -LiteralPath $scriptsSource -PathType Container)) {
    throw "Missing $scriptsSource"
}

$helpers = Get-ChildItem -LiteralPath $scriptsSource -Filter "*.py" -File
if ($helpers.Count -eq 0) {
    throw "No Python helper scripts found in $scriptsSource"
}

Install-File -Source $agentsSource -Destination (Join-Path $HOME ".codex/AGENTS.md")
Install-File -Source $agentsSource -Destination (Join-Path $HOME ".claude/CLAUDE.md")
Install-File -Source $agentsSource -Destination (Join-Path $HOME ".pi/agent/AGENTS.md")
Install-File -Source $agentsSource -Destination (Join-Path $HOME ".gemini/GEMINI.md")

$helpersDest = Join-Path $HOME ".agents/scripts"
Invoke-Step -Description "New-Item -ItemType Directory '$helpersDest'" -Action {
    New-Item -ItemType Directory -Path $helpersDest -Force | Out-Null
}

foreach ($helper in $helpers) {
    Install-File -Source $helper.FullName -Destination (Join-Path $helpersDest $helper.Name)
}

Write-Step "Done."
Write-Step "Antigravity global rules installed at ~/.gemini/GEMINI.md; shared Antigravity skills use a separate path."
