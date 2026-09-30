$ErrorActionPreference = "Stop"
$ServiceRoot = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ServiceRoot
$ExpectedPython = @(
    (Join-Path $ProjectRoot "runtime\model-env\python.exe"),
    (Join-Path $ProjectRoot "runtime\model-env\Scripts\python.exe")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$PidFile = Join-Path $ServiceRoot ".local-models.pids.json"
if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "No local model PID record was found."
    exit 0
}
$saved = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
foreach ($property in $saved.PSObject.Properties) {
    $pidValue = [int]$property.Value
    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($process -and $process.Path -eq $ExpectedPython) {
        Stop-Process -Id $pidValue -Force
        Write-Host "Stopped $($property.Name) (PID=$pidValue)."
    } elseif ($process) {
        Write-Warning "Skipped reused PID $pidValue because it is not a Warm Companion model process."
    }
}
Remove-Item -LiteralPath $PidFile -Force
