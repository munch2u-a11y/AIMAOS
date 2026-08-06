[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $SetupArguments
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Push-Location $Root
try {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & $PyLauncher.Source -3 -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)"
        if ($LASTEXITCODE -ne 0) { throw "AIMAOS requires Python 3.11 through 3.13." }
        & $PyLauncher.Source -3 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Could not create the AIMAOS virtual environment." }
    }
    elseif ($Python) {
        & $Python.Source -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)"
        if ($LASTEXITCODE -ne 0) { throw "AIMAOS requires Python 3.11 through 3.13." }
        & $Python.Source -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Could not create the AIMAOS virtual environment." }
    }
    else {
        throw "Python was not found. Install Python 3.11 through 3.13, then run this installer again."
    }

    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not update pip in the AIMAOS virtual environment." }
    & $VenvPython -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw "Could not install AIMAOS dependencies." }
    & $VenvPython doctor.py
    if ($LASTEXITCODE -ne 0) { throw "AIMAOS diagnostics reported a blocking failure." }
    & $VenvPython setup.py @SetupArguments
    if ($LASTEXITCODE -ne 0) { throw "AIMAOS setup did not complete successfully." }
    & $VenvPython doctor.py
    if ($LASTEXITCODE -ne 0) { throw "AIMAOS diagnostics reported a blocking failure after setup." }

    Write-Host ""
    Write-Host "Installation complete. Start AIMAOS with 'Launch AIMAOS.cmd'." -ForegroundColor Green
}
finally {
    Pop-Location
}
