param([int]$Port = 8002)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$candidates = @(
    (Join-Path $Root "runtime\backend-env\python.exe"),
    (Join-Path $Root "runtime\backend-env\Scripts\python.exe")
)
$Python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Python) { throw "Missing backend Python environment under runtime\backend-env." }
$env:NUANBAN_PORT = [string]$Port
& $Python (Join-Path $Root "backend\run.py")
