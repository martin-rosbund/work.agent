param([switch]$NoBrowser, [switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
function Random-Key([int]$Length) {
    $buffer = New-Object byte[] $Length
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($buffer).Replace('+','-').Replace('/','_')
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Bitte Docker Desktop mit Linux-Containern installieren und starten.' }
New-Item -ItemType Directory -Force -Path '.secrets', 'data', 'data/originals', 'data/knowledge' | Out-Null
if (-not (Test-Path -LiteralPath '.secrets/master_key')) { [IO.File]::WriteAllText((Join-Path $PWD '.secrets/master_key'), (Random-Key 32)) }
if (-not (Test-Path -LiteralPath '.secrets/setup_token')) { [IO.File]::WriteAllText((Join-Path $PWD '.secrets/setup_token'), (Random-Key 32)) }
if (-not (Test-Path -LiteralPath '.env')) {
    $databasePassword = (Random-Key 36).TrimEnd('=')
    [IO.File]::WriteAllText((Join-Path $PWD '.env'), "POSTGRES_PASSWORD=$databasePassword`nAPP_PORT=8080`nAPP_ORIGIN=http://localhost:8080`n")
}
# Restrict secret files to the signed-in Windows account, SYSTEM and administrators.
if ($env:OS -eq 'Windows_NT') {
    $account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls '.secrets' /inheritance:r /grant:r "${account}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Dateirechte fuer .secrets konnten nicht gesetzt werden.' }
    & icacls '.env' /inheritance:r /grant:r "${account}:F" '*S-1-5-18:F' '*S-1-5-32-544:F' /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Dateirechte fuer .env konnten nicht gesetzt werden.' }
}
if ($PrepareOnly) { Write-Host 'Lokale Konfiguration vorbereitet.'; exit 0 }
& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop starten und das Skript erneut ausfuehren.' }
& docker compose up -d --build --wait --wait-timeout 240
if ($LASTEXITCODE -ne 0) { throw 'Start fehlgeschlagen. Details: docker compose logs --tail 100' }
$originLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^APP_ORIGIN=' } | Select-Object -First 1
$origin = if ($originLine) { $originLine.Substring(11).Trim() } else { 'http://localhost:8080' }
Write-Host "Work Agent ist bereit: $origin"
if (-not $NoBrowser) {
    $state = Invoke-RestMethod "$origin/api/v1/auth/status"
    $url = $origin
    if (-not $state.initialized) { $url += '/#setup=' + [Uri]::EscapeDataString((Get-Content -Raw -LiteralPath '.secrets/setup_token').Trim()) }
    Start-Process $url
}
