param([switch]$RestartOwned, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$localProvider = & ./.venv/Scripts/python.exe -c "from backend.config import settings; print(settings.ai_provider)"
if ($localProvider -eq 'ollama') { & "$PSScriptRoot/start-ollama.ps1" }
$launchArgs = @('scripts/serve.py', '--port', "$Port")
if ($RestartOwned) { $launchArgs += '--restart-owned' }
for ($attempt = 1; $attempt -le 3; $attempt++) {
    & ./.venv/Scripts/python.exe @launchArgs
    if ($LASTEXITCODE -ne 74) { break }
    if ($attempt -lt 3) {
        Write-Host 'Retrying Windows socket initialization...'
        Start-Sleep -Milliseconds 500
    }
}
if ($LASTEXITCODE -ne 0) { throw 'ScholarPilot did not start. See the diagnostic above.' }
