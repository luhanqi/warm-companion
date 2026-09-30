param([string]$Root = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = "Stop"
$required = @(
    "README.md", ".env.example", "backend\run.py", "start-backend.ps1", "web\login.html",
    "train\outputs\sft-1.5b\adapter\adapter_model.safetensors",
    "models\Qwen2.5-1.5B-Instruct\config.json",
    "models\SenseVoiceSmall\model.pt", "models\fsmn-vad\model.pt",
    "models\bge-m3", "models\bge-reranker-v2-m3",
    "models\Qwen2-VL-2B-Instruct\model-00001-of-00002.safetensors",
    "models\Fun-CosyVoice3-0.5B-2512", "models\Wan2.2-TI2V-5B"
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Root $_)) })
$forbidden = @(Get-ChildItem -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.FullName -notlike (Join-Path $Root "runtime\*") -and
    ($_.Name -in @(".env", "__pycache__", ".venv", "node_modules") -or $_.Extension -in @(".pyc", ".pid", ".db", ".sqlite", ".sqlite3"))
})
Write-Host "Submission root: $Root"
Write-Host "Missing items: $($missing.Count)"
$missing | ForEach-Object { Write-Host "  MISSING $_" -ForegroundColor Red }
Write-Host "Forbidden items: $($forbidden.Count)"
$forbidden | ForEach-Object { Write-Host "  FORBIDDEN $($_.FullName)" -ForegroundColor Yellow }
if ($missing.Count -or $forbidden.Count) { exit 1 }
Write-Host "Submission structure check passed." -ForegroundColor Green
