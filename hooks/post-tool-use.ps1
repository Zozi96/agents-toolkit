$ErrorActionPreference = "Stop"

# Drain stdin first: exiting before reading it makes the harness's payload
# write fail with "failed to write hook stdin: Broken pipe".
# Pipeline input arrives via $input when invoked in-process (& script.ps1);
# process stdin via [Console]::In when spawned as a child (real hook usage).
$payload = @($input) -join "`n"
if (-not $payload) { $payload = [Console]::In.ReadToEnd() }

$python = $null
$pythonArgs = @()
foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
    $extra = if ($candidate.Count -gt 1) { $candidate[1..($candidate.Count - 1)] } else { @() }
    $probe = (& $candidate[0] @extra -c "print('ok')" 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $probe -eq "ok") {
        $python = $candidate[0]
        $pythonArgs = $extra
        break
    }
}
if (-not $python) { throw "Python 3 is required" }

$root = if ($env:CLAUDE_PLUGIN_ROOT) { $env:CLAUDE_PLUGIN_ROOT } else { $env:PLUGIN_ROOT }
if (-not $root) { exit 0 }
$payload | & $python @pythonArgs (Join-Path $root "hooks/post-tool-use.py")
exit $LASTEXITCODE
