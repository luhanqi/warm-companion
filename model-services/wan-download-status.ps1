param([string]$ModelRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "models"))

$Target = Join-Path $ModelRoot "Wan2.2-TI2V-5B"
$required = @(
    "diffusion_pytorch_model-00001-of-00003.safetensors",
    "diffusion_pytorch_model-00002-of-00003.safetensors",
    "diffusion_pytorch_model-00003-of-00003.safetensors",
    "models_t5_umt5-xxl-enc-bf16.pth",
    "Wan2.2_VAE.pth"
)
$downloaded = if (Test-Path -LiteralPath $Target) { (Get-ChildItem -LiteralPath $Target -Recurse -File | Measure-Object Length -Sum).Sum } else { 0 }
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Target $_)) })
[pscustomobject]@{
    Complete = ($missing.Count -eq 0)
    DownloadedGB = [math]::Round($downloaded / 1GB, 2)
    MissingFiles = ($missing -join ", ")
    ModelDirectory = $Target
} | Format-List
