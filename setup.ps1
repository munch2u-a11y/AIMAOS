[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $SetupArguments
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "AIMAOS is not installed yet. Run install.cmd first."
}

Push-Location $Root
try {
    & $VenvPython setup.py @SetupArguments
    if ($LASTEXITCODE -ne 0) { throw "AIMAOS setup did not complete successfully." }
}
finally {
    Pop-Location
}
