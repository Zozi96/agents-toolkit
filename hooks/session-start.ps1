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
$payload = [Console]::In.ReadToEnd()
if (-not $env:PLUGIN_ROOT) { throw "PLUGIN_ROOT is required" }
$payload | & $python @pythonArgs (Join-Path $env:PLUGIN_ROOT "hooks/session-start.py")
exit $LASTEXITCODE
