$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source -3 (Join-Path $root "serve-demo.py")
    exit $LASTEXITCODE
}
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python 3 was not found. Install Python 3 or run any static HTTP server with the site directory as its root."
}
& $python.Source (Join-Path $root "serve-demo.py")
exit $LASTEXITCODE
