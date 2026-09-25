$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
& (Join-Path $PSScriptRoot 'backup.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Update wegen fehlgeschlagenem Backup abgebrochen.' }
& docker compose build --pull
if ($LASTEXITCODE -ne 0) { throw 'Build fehlgeschlagen. Vorhandene Daten bleiben erhalten.' }
& docker compose up -d --wait --wait-timeout 240
if ($LASTEXITCODE -ne 0) { throw 'Start fehlgeschlagen. Backup fuer Wiederherstellung verwenden.' }
Write-Host 'Update aus dem aktuellen Projektstand abgeschlossen.'
