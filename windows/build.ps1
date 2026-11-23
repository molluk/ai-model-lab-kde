# Build the experimental Windows desktop shell (PowerShell 5.1+).
# This does NOT yet make Linux-specific process management Windows-compatible.
param(
    [switch]$SkipInstall
)
$ErrorActionPreference = "Stop"
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "This build must run on Windows."
}
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $Root
try {
    if (-not $SkipInstall) {
        python -m pip install --requirement "windows/requirements-build.txt"
        if ($LASTEXITCODE -ne 0) { throw "Could not install build dependencies." }
    }
    python release_preflight.py
    if ($LASTEXITCODE -ne 0) { throw "Release preflight failed." }
    python -m unittest discover -s tests -p "test_windows_bootstrap.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Windows bootstrap tests failed." }

    python version_info.py --source $Root --write (Join-Path $Root "build_info.json")
    if ($LASTEXITCODE -ne 0) { throw "Failed to embed build revision." }

    $Data = @(
        "build_info.json;.",
        "assets;assets",
        "locales;locales",
        "docs;docs",
        "models.example.json;.",
        "settings.example.json;.",
        "services.example.json;.",
        "extensions;extensions",
        "benchmarks;benchmarks"
    )
    $Args = @("--noconfirm", "--clean", "--onedir", "--windowed",
              "--name", "AI-Model-Lab")
    foreach ($Item in $Data) { $Args += @("--add-data", $Item) }
    $Args += "gui.py"
    python -m PyInstaller @Args
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    $Exe = Join-Path $Root "dist/AI-Model-Lab/AI-Model-Lab.exe"
    if (-not (Test-Path $Exe)) { throw "Missing Windows executable: $Exe" }
    Write-Host "Built experimental Windows shell: $Exe"
    Write-Host "NOT RELEASE READY: model/service process management still requires Windows support."
}
finally {
    Pop-Location
}
