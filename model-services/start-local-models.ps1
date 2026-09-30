param(
    [string]$ModelRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "models"),
    [string]$Python = "",
    [ValidateSet("speech", "rag", "vision", "standard", "all")]
    [string]$Services = "standard",
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"
$ServiceRoot = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $Python = @(
        (Join-Path $ProjectRoot "runtime\model-env\python.exe"),
        (Join-Path $ProjectRoot "runtime\model-env\Scripts\python.exe")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
$PidFile = Join-Path $ServiceRoot ".local-models.pids.json"

function Test-ModelService([string]$Url) {
    try {
        $status = Invoke-RestMethod -Uri $Url -TimeoutSec 2
        return $status.status -eq "ok"
    } catch { return $false }
}

if (-not (Test-Path -LiteralPath $Python)) { throw "Missing runtime model environment: $Python" }
$selected = if ($Services -eq "standard") { @("speech", "rag") } elseif ($Services -eq "all") { @("speech", "rag", "vision") } else { @($Services) }
$required = @()
if ("speech" -in $selected) { $required += @((Join-Path $ModelRoot "SenseVoiceSmall\model.pt"), (Join-Path $ModelRoot "fsmn-vad\model.pt")) }
if ("rag" -in $selected) { $required += @((Join-Path $ModelRoot "bge-m3"), (Join-Path $ModelRoot "bge-reranker-v2-m3")) }
if ("vision" -in $selected) { $required += @((Join-Path $ModelRoot "Qwen2-VL-2B-Instruct\model-00001-of-00002.safetensors"), (Join-Path $ModelRoot "Qwen2-VL-2B-Instruct\model-00002-of-00002.safetensors")) }
foreach ($path in $required) { if (-not (Test-Path -LiteralPath $path)) { throw "Missing model file: $path" } }

$env:NUANBAN_MODEL_ROOT = $ModelRoot
$env:SENSEVOICE_MODEL_DIR = Join-Path $ModelRoot "SenseVoiceSmall"
$env:VAD_MODEL_DIR = Join-Path $ModelRoot "fsmn-vad"
$env:SPEECH_DEVICE = "cpu"
$env:BGE_MODEL_DIR = Join-Path $ModelRoot "bge-m3"
$env:RERANK_MODEL_DIR = Join-Path $ModelRoot "bge-reranker-v2-m3"
$env:VISION_MODEL_DIR = Join-Path $ModelRoot "Qwen2-VL-2B-Instruct"
$env:VISION_MODEL_NAME = "Qwen/Qwen2-VL-2B-Instruct"
$env:MODELSCOPE_CACHE = Join-Path $ModelRoot "cache"
$env:HF_HOME = Join-Path $ModelRoot "hf-cache"

if ($Foreground) {
    if ($selected.Count -ne 1) { throw "Foreground mode requires exactly one service." }
    $foregroundScript = @{ speech = "speech_service.py"; rag = "rag_service.py"; vision = "vision_service.py" }[$selected[0]]
    & $Python (Join-Path $ServiceRoot $foregroundScript)
    exit $LASTEXITCODE
}

$savedPids = @{}
if (Test-Path -LiteralPath $PidFile) {
    try {
        $previous = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
        foreach ($property in $previous.PSObject.Properties) {
            $savedPids[$property.Name] = [int]$property.Value
        }
    } catch { $savedPids = @{} }
}
$serviceDefinitions = @(
    @{ Name = "speech"; Port = 8003; Script = "speech_service.py"; Log = "speech-service.log" },
    @{ Name = "rag"; Port = 8004; Script = "rag_service.py"; Log = "rag-service.log" },
    @{ Name = "vision"; Port = 8005; Script = "vision_service.py"; Log = "vision-service.log" }
)
$servicesToStart = @($serviceDefinitions | Where-Object { $_.Name -in $selected })
foreach ($service in $servicesToStart) {
    $healthUrl = "http://127.0.0.1:$($service.Port)/health"
    if (Test-ModelService $healthUrl) { Write-Host "$($service.Name) is already running: $healthUrl"; continue }
    $logPath = Join-Path $ServiceRoot $service.Log
    $env:PORT = [string]$service.Port
    $process = Start-Process -FilePath $Python -ArgumentList @((Join-Path $ServiceRoot $service.Script)) -WorkingDirectory $ServiceRoot -WindowStyle Hidden -RedirectStandardOutput $logPath -RedirectStandardError ($logPath + ".err") -PassThru
    $savedPids[$service.Name] = $process.Id
    for ($attempt = 0; $attempt -lt 60 -and -not (Test-ModelService $healthUrl); $attempt++) {
        $process.Refresh(); if ($process.HasExited) { break }; Start-Sleep -Milliseconds 500
    }
    if (-not (Test-ModelService $healthUrl)) { throw "$($service.Name) failed to start. Check $($logPath).err" }
    Write-Host "$($service.Name) is ready: $healthUrl"
}
$savedPids | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding UTF8
