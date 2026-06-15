param(
    [string]$RawBase = $env:RAW_BASE,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RawBase)) {
    $RawBase = "https://raw.githubusercontent.com/Zozi96/agents-toolkit/main"
}

$RawBase = $RawBase.TrimEnd("/")
$files = @(
    "AGENTS.md",
    "install-agents.ps1",
    "scripts/_agent_utils.py",
    "scripts/agent_context.py",
    "scripts/compact_logs.py",
    "scripts/diff_summary.py",
    "scripts/repo_map.py",
    "scripts/safe_read.py",
    "scripts/scan_errors.py",
    "scripts/summarize_data.py",
    "scripts/summarize_json.py",
    "scripts/summarize_tests.py"
)

function Save-RemoteFile {
    param(
        [string]$Url,
        [string]$Destination
    )

    $dir = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Invoke-WebRequest -Uri $Url -OutFile $Destination
}

$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agents-toolkit-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

try {
    foreach ($file in $files) {
        Save-RemoteFile -Url "$RawBase/$file" -Destination (Join-Path $tmpDir $file)
    }

    $installArgs = @{}
    if ($DryRun) {
        $installArgs["DryRun"] = $true
    }

    & (Join-Path $tmpDir "install-agents.ps1") @installArgs
    Write-Host "Downloaded from: $RawBase"
}
finally {
    Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}
