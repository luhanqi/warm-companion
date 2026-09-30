param(
    [string]$ModelRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "models"),
    [string]$Python = ""
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
$Downloader = Join-Path $ServiceRoot "download_wan.py"
$PidFile = Join-Path $ServiceRoot ".wan-download.pid"
$Log = Join-Path $ServiceRoot "wan-download.log"
$ErrorLog = Join-Path $ServiceRoot "wan-download.log.err"
$Target = Join-Path $ModelRoot "Wan2.2-TI2V-5B"
$required = @(
    "diffusion_pytorch_model-00001-of-00003.safetensors",
    "diffusion_pytorch_model-00002-of-00003.safetensors",
    "diffusion_pytorch_model-00003-of-00003.safetensors",
    "models_t5_umt5-xxl-enc-bf16.pth",
    "Wan2.2_VAE.pth"
)
if (@($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Target $_)) }).Count -eq 0) {
    Write-Host "Wan2.2-TI2V-5B is already complete: $Target"
    exit 0
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Missing runtime model environment: $Python" }
$env:NUANBAN_MODEL_ROOT = $ModelRoot
$env:MODELSCOPE_CACHE = Join-Path $ModelRoot "cache"
$process = Start-Process -FilePath $Python -ArgumentList @($Downloader) -WorkingDirectory $ServiceRoot -WindowStyle Hidden -RedirectStandardOutput $Log -RedirectStandardError $ErrorLog -PassThru
Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ASCII
Write-Host "Wan model download started in background (PID=$($process.Id))."
