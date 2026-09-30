param(
  [switch]$Smoke,
  [switch]$Cpu
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  py -3.12 -m venv .venv
}

$py = ".\.venv\Scripts\python.exe"

& $py -m pip install --upgrade pip
if ($Cpu) {
  & $py -m pip install torch --index-url https://download.pytorch.org/whl/cpu
} else {
  & $py -m pip install torch --index-url https://download.pytorch.org/whl/cu124
}
& $py -m pip install -r requirements.txt

& $py prepare_data.py
if ($Smoke) {
  & $py train_sft.py --smoke
} else {
  & $py train_sft.py
}
