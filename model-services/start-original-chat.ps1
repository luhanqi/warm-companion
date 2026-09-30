param(
    [string]$Python = "",
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $Python = @(
        (Join-Path $ProjectRoot "runtime\model-env\python.exe"),
        (Join-Path $ProjectRoot "runtime\model-env\Scripts\python.exe")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
$Server = Join-Path $ProjectRoot "train\serve.py"
$Adapter = Join-Path $ProjectRoot "train\outputs\sft-1.5b\adapter"
$PidFile = Join-Path $PSScriptRoot ".original-chat.pid"
$Log = Join-Path $PSScriptRoot "original-chat.log"
function Test-OriginalChat { try { return [bool](Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $Port) -TimeoutSec 2).ok } catch { return $false } }
if (Test-OriginalChat) { Write-Host "Local chat model is already running: http://127.0.0.1:$Port"; exit 0 }
if (-not (Test-Path -LiteralPath $Python)) { throw "Missing runtime model environment: $Python" }
foreach ($path in @($Server, (Join-Path $Adapter "adapter_model.safetensors"), (Join-Path $Adapter "nuanban_meta.json"))) { if (-not (Test-Path -LiteralPath $path)) { throw "Missing file: $path" } }
$process = Start-Process -FilePath $Python -ArgumentList @($Server, "--adapter", $Adapter, "--port", [string]$Port) -WorkingDirectory (Join-Path $ProjectRoot "train") -WindowStyle Hidden -RedirectStandardOutput $Log -RedirectStandardError ($Log + ".err") -PassThru
Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ASCII
for ($attempt = 0; $attempt -lt 180; $attempt++) {
    if (Test-OriginalChat) { Write-Host "Local chat model is ready: http://127.0.0.1:$Port"; exit 0 }
    $process.Refresh(); if ($process.HasExited) { throw "Local chat model failed to start. Check $($Log).err" }; Start-Sleep -Seconds 1
}
throw "Chat model load exceeded 180 seconds. Check $($Log).err"
