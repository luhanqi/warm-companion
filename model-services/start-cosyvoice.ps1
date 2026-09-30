param(
    [string]$Python = "",
    [int]$Port = 50000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $Python = @(
        (Join-Path $ProjectRoot "runtime\cosyvoice-env\python.exe"),
        (Join-Path $ProjectRoot "runtime\cosyvoice-env\Scripts\python.exe")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
$Repo = Join-Path $ProjectRoot "runtime\vendor\CosyVoice"
$Model = Join-Path $ProjectRoot "models\Fun-CosyVoice3-0.5B-2512"
$Bridge = Join-Path $PSScriptRoot "cosyvoice_bridge.py"
$PidFile = Join-Path $PSScriptRoot ".cosyvoice.pid"
$Log = Join-Path $PSScriptRoot "cosyvoice-service.log"

function Test-CosyVoice {
    try {
        return (Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $Port) -TimeoutSec 2).status -eq "ok"
    } catch { return $false }
}

if (Test-CosyVoice) { Write-Host "CosyVoice is already running: http://127.0.0.1:$Port"; exit 0 }
foreach ($path in @($Python, $Bridge, (Join-Path $Repo "cosyvoice\cli\cosyvoice.py"), (Join-Path $Repo "third_party\Matcha-TTS\matcha"), (Join-Path $Model "cosyvoice3.yaml"))) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing CosyVoice file: $path" }
}
$env:COSYVOICE_REPO = $Repo
$env:COSYVOICE_MODEL_DIR = $Model
$env:HF_HOME = Join-Path $ProjectRoot "runtime\hf-cache-cosy"
$env:PORT = [string]$Port
$process = Start-Process -FilePath $Python -ArgumentList @($Bridge) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $Log -RedirectStandardError ($Log + ".err") -PassThru
Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ASCII
for ($attempt = 0; $attempt -lt 240; $attempt++) {
    if (Test-CosyVoice) { Write-Host "CosyVoice is ready: http://127.0.0.1:$Port"; exit 0 }
    $process.Refresh()
    if ($process.HasExited) { throw "CosyVoice failed to start. Check $($Log).err" }
    Start-Sleep -Seconds 1
}
throw "CosyVoice load exceeded 240 seconds. Check $($Log).err"
