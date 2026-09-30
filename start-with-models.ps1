param(
    [int]$Port = 8002,
    [ValidateSet("backend", "chat", "speech", "rag", "vision", "cosyvoice", "standard", "all")]
    [string]$Profile = "standard"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:NUANBAN_AUTO_START_MODELS = "0"

if ($Profile -in @("chat", "standard", "all")) {
    & (Join-Path $Root "model-services\start-original-chat.ps1")
    $env:LLM_BASE_URL = "http://127.0.0.1:8001/v1"
    $env:LLM_API_KEY = "local"
    $env:LLM_MODEL = "nuanban"
}
if ($Profile -in @("speech", "rag", "vision", "standard", "all")) {
    & (Join-Path $Root "model-services\start-local-models.ps1") -Services $Profile
}
if ($Profile -in @("speech", "standard", "all")) {
    $env:SPEECH_BASE_URL = "http://127.0.0.1:8003"
    $env:ACOUSTIC_BASE_URL = "http://127.0.0.1:8003"
}
if ($Profile -in @("rag", "standard", "all")) {
    $env:EMBEDDING_BASE_URL = "http://127.0.0.1:8004/v1"
    $env:RERANK_BASE_URL = "http://127.0.0.1:8004/v1"
    $env:EMBEDDING_API_KEY = "local"
    $env:RERANK_API_KEY = "local"
}
if ($Profile -in @("vision", "all")) {
    $env:VISION_BASE_URL = "http://127.0.0.1:8005/v1"
    $env:VISION_API_KEY = "local"
    $env:VISION_MODEL = "Qwen/Qwen2-VL-2B-Instruct"
}
if ($Profile -in @("cosyvoice", "all")) {
    & (Join-Path $Root "model-services\start-cosyvoice.ps1")
    $env:COSYVOICE_BASE_URL = "http://127.0.0.1:50000"
}
if ($Profile -eq "all") {
    Write-Warning "This profile can exceed 30 GB of memory during concurrent inference. Use standard, vision, or cosyvoice on a 16 GB computer."
    Write-Warning "Wan2.2 additionally needs an NVIDIA GPU with at least 24 GB VRAM and is not started here."
}
$env:NUANBAN_PORT = [string]$Port
& (Join-Path $Root "start-backend.ps1") -Port $Port
