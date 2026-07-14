$ErrorActionPreference = "Stop"

$python = if (Get-Command py -ErrorAction SilentlyContinue) {
    "py"
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    "python"
}
elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    "python3"
}
else {
    throw "Python 3 is required"
}
$pythonArgs = if ($python -eq "py") { @("-3") } else { @() }
# Pipeline input arrives via $input when invoked in-process (& script.ps1);
# process stdin via [Console]::In when spawned as a child (real hook usage).
$payload = @($input) -join "`n"
if (-not $payload) { $payload = [Console]::In.ReadToEnd() }
$root = if ($env:CLAUDE_PLUGIN_ROOT) { $env:CLAUDE_PLUGIN_ROOT } else { $env:PLUGIN_ROOT }
if (-not $root) { throw "CLAUDE_PLUGIN_ROOT or PLUGIN_ROOT is required" }
$payload | & $python @pythonArgs (Join-Path $root "hooks/pre-tool-use.py")
exit $LASTEXITCODE
