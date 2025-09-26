param(
  [string]$Py = "python"
)

$ErrorActionPreference = "Stop"

& $Py -m venv .venv
.\.venv\Scripts\activate
& $Py -m pip install --upgrade pip setuptools wheel
& $Py -m pip install -r requirements.txt

Write-Host "`nSanity check:" -ForegroundColor Cyan
& $Py sanity_check.py

Write-Host "`nRun:  python backend\run_local.py" -ForegroundColor Green
