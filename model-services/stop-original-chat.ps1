$ErrorActionPreference = "Stop"
$ServiceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ServiceRoot ".original-chat.pid"
$ProjectRoot = Split-Path -Parent $ServiceRoot
$ExpectedPython = @(
    (Join-Path $ProjectRoot "runtime\model-env\python.exe"),
    (Join-Path $ProjectRoot "runtime\model-env\Scripts\python.exe")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "No local chat PID file was found."
    exit 0
}

$processId = [int](Get-Content -LiteralPath $PidFile -Raw)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if ($process -and $process.Path -eq $ExpectedPython) {
    Stop-Process -Id $processId -Force
    Write-Host "Stopped local chat model (PID=$processId)."
} elseif ($process) {
    Write-Warning "Skipped reused PID $processId because it is not the Warm Companion chat process."
}
Remove-Item -LiteralPath $PidFile -Force
