param([string]$BackupPath, [string]$DataPath)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location $workspace
if (-not $DataPath) { $DataPath = Join-Path $workspace 'data' }
$dataSource = (Resolve-Path -LiteralPath $DataPath).Path
if (-not $BackupPath) { $BackupPath = Join-Path $workspace ('backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$target = [IO.Path]::GetFullPath($BackupPath)
if (Test-Path -LiteralPath $target) { throw 'Das Sicherungsziel existiert bereits. Bitte einen neuen Ordner angeben.' }
$keyTarget = $target + '.keys'
if (Test-Path -LiteralPath $keyTarget) { throw 'Der Schluesselordner existiert bereits.' }
New-Item -ItemType Directory -Path $target, $keyTarget | Out-Null
$succeeded = $false
try {
    & docker compose stop api worker
    if ($LASTEXITCODE -ne 0) { throw 'Dienste konnten nicht fuer das Backup angehalten werden.' }
    & docker compose exec -T db pg_dump -U workagent -d workagent --no-owner --no-acl -f /tmp/workagent-backup.sql
    if ($LASTEXITCODE -ne 0) { throw 'Datenbanksicherung fehlgeschlagen.' }
    & docker compose cp 'db:/tmp/workagent-backup.sql' (Join-Path $target 'database.sql')
    if ($LASTEXITCODE -ne 0) { throw 'Datenbanksicherung konnte nicht kopiert werden.' }
    Copy-Item -LiteralPath $dataSource -Destination (Join-Path $target 'data') -Recurse
    Copy-Item -LiteralPath (Join-Path $workspace '.secrets') -Destination (Join-Path $keyTarget '.secrets') -Recurse
    Copy-Item -LiteralPath (Join-Path $workspace '.env') -Destination (Join-Path $keyTarget '.env')
    if ($env:OS -eq 'Windows_NT') {
        $account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls $keyTarget /inheritance:r /grant:r "${account}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Schluesselsicherung konnte nicht geschuetzt werden.' }
    }
    [IO.File]::WriteAllText((Join-Path $target 'manifest.json'), (@{ version = 1; createdAt = (Get-Date).ToUniversalTime().ToString('o'); database = 'PostgreSQL 17'; keys = 'Separate .keys directory; required for restore' } | ConvertTo-Json))
    $hashes = Get-ChildItem -LiteralPath $target -File -Recurse | ForEach-Object { @{ path = $_.FullName.Substring($target.Length + 1); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash } }
    [IO.File]::WriteAllText((Join-Path $target 'checksums.json'), (ConvertTo-Json -InputObject @($hashes)))
    $succeeded = $true
} finally {
    & docker compose start api worker
}
if ($succeeded) {
    Write-Host "Backup erstellt: $target"
    Write-Host "Schluessel separat sichern: $keyTarget"
}
