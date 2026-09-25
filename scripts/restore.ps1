param([Parameter(Mandatory=$true)][string]$BackupPath, [string]$KeyPath)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location $workspace
$backup = (Resolve-Path -LiteralPath $BackupPath).Path
if (-not $KeyPath) { $KeyPath = $backup + '.keys' }
$keys = (Resolve-Path -LiteralPath $KeyPath).Path
foreach ($required in @('database.sql','manifest.json','checksums.json','data')) {
    if (-not (Test-Path -LiteralPath (Join-Path $backup $required))) { throw "Unvollstaendiges Backup: $required fehlt." }
}
foreach ($required in @('.env','.secrets/master_key','.secrets/setup_token')) {
    if (-not (Test-Path -LiteralPath (Join-Path $keys $required))) { throw "Schluesselsicherung unvollstaendig: $required fehlt." }
}
foreach ($entry in (Get-Content -Raw -LiteralPath (Join-Path $backup 'checksums.json') | ConvertFrom-Json)) {
    $file = [IO.Path]::GetFullPath((Join-Path $backup $entry.path))
    if (-not $file.StartsWith($backup.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Ungueltiger Dateipfad im Backup.' }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) { throw "Pruefsumme stimmt nicht: $($entry.path)" }
}
if ((Test-Path -LiteralPath 'data') -and (Get-ChildItem -LiteralPath 'data' -Recurse -File | Select-Object -First 1)) { throw 'Wiederherstellung nur in eine frische Installation mit leerem Datenordner. Vorhandene Daten werden nicht ueberschrieben.' }
if (Test-Path -LiteralPath '.env') {
    $running = & docker compose ps -q db
    if ($running) {
        $existingCount = & docker compose exec -T db psql -U workagent -d workagent -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
        if ($LASTEXITCODE -ne 0 -or [int]$existingCount -gt 0) { throw 'Bestehende Datenbank gefunden. Konfiguration und Daten bleiben unveraendert.' }
    } else {
        throw 'Ziel enthaelt bereits eine Konfiguration. Fuer die Wiederherstellung einen neuen Projektordner ohne .env verwenden.'
    }
}
# The SQL is restored only into an empty database. Never drop an existing database.
Copy-Item -LiteralPath (Join-Path $keys '.env') -Destination (Join-Path $workspace '.env') -Force
Copy-Item -LiteralPath (Join-Path $keys '.secrets') -Destination $workspace -Recurse -Force
& docker compose up -d db --wait
if ($LASTEXITCODE -ne 0) { throw 'Datenbank konnte nicht gestartet werden.' }
$count = & docker compose exec -T db psql -U workagent -d workagent -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
if ($LASTEXITCODE -ne 0 -or [int]$count -gt 0) { throw 'Zieldatenbank ist nicht leer. Bitte eine frische Installation verwenden.' }
& docker compose cp (Join-Path $backup 'database.sql') 'db:/tmp/workagent-restore.sql'
if ($LASTEXITCODE -ne 0) { throw 'SQL-Sicherung konnte nicht kopiert werden.' }
& docker compose exec -T db psql -v ON_ERROR_STOP=1 -U workagent -d workagent -f /tmp/workagent-restore.sql
if ($LASTEXITCODE -ne 0) { throw 'Datenbankwiederherstellung fehlgeschlagen.' }
New-Item -ItemType Directory -Force -Path (Join-Path $workspace 'data') | Out-Null
Get-ChildItem -LiteralPath (Join-Path $backup 'data') | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $workspace 'data') -Recurse -Force }
& docker compose up -d --build --wait
if ($LASTEXITCODE -ne 0) { throw 'Daten wiederhergestellt, aber Anwendung startet nicht. Bitte Logs pruefen.' }
Write-Host 'Wiederherstellung abgeschlossen. Anmeldung mit dem bisherigen lokalen Passwort.'
