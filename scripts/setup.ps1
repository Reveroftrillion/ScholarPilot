$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m venv .venv --without-pip
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
python -m pip --python .venv/Scripts/python.exe install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
Write-Host 'Ready. Run: .\scripts\start.ps1'
