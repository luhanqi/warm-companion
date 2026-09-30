$ErrorActionPreference = "Stop"
$PidFile = Join-Path $PSScriptRoot ".cosyvoice.pid"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExpectedPython = @(
    (Join-Path $ProjectRoot "runtime\cosyvoice-env\python.exe"),
    (Join-Path $ProjectRoot "runtime\cosyvoice-env\Scripts\python.exe")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "No CosyVoice PID file was found."
    exit 0
}
$processId = [int](Get-Content -LiteralPath $PidFile -Raw)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if ($process -and $process.Path -eq $ExpectedPython) {
    Stop-Process -Id $processId -Force
    Write-Host "Stopped CosyVoice (PID=$processId)."
} elseif ($process) {
    Write-Warning "Skipped reused PID $processId because it is not the Warm Companion CosyVoice process."
}
Remove-Item -LiteralPath $PidFile -Force
