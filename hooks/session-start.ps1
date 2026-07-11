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
$hookRoot = if ($env:PLUGIN_ROOT) { $env:PLUGIN_ROOT } else { Join-Path $HOME ".agents" }
$payload | & $python @pythonArgs (Join-Path $hookRoot "hooks/session-start.py")
exit $LASTEXITCODE
