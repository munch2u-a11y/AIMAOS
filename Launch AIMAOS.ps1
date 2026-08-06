$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "AIMAOS is not installed yet. Run install.cmd first."
}

Push-Location $Root
try {
    & $VenvPython aimaos_ui.py
    if ($LASTEXITCODE -ne 0) { throw "AIMAOS stopped because the workstation process failed." }
}
finally {
    Pop-Location
}
