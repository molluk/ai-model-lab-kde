# Development only, not an installer.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $Root
try {
    python -m pip install --requirement "windows/requirements-build.txt"
    if ($LASTEXITCODE -ne 0) { throw "Dependencies installation failed." }
    python gui.py
    if ($LASTEXITCODE -ne 0) { throw "AI Model Lab exited with an error." }
}
finally {
    Pop-Location
}
