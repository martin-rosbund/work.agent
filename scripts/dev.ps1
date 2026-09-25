param([ValidateSet('up','down','restart','prepare')][string]$Action = 'up', [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$compose = @('compose', '--env-file', '.local/dev/environment', '-f', 'compose.dev.yaml')
if ($Action -eq 'down') {
    if (Test-Path '.local/dev/environment') {
        & docker @compose stop
        if ($LASTEXITCODE -ne 0) { throw 'Entwicklungscontainer konnten nicht gestoppt werden.' }
    }
    exit 0
}
function New-Secret([int]$length) {
    $bytes = New-Object byte[] $length
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_')
}
New-Item -ItemType Directory -Force '.local/dev/secrets', '.local/dev/data' | Out-Null
foreach ($name in @('master_key', 'setup_token')) {
    $path = Join-Path $PWD ".local/dev/secrets/$name"
    if (-not (Test-Path -LiteralPath $path)) { [IO.File]::WriteAllText($path, (New-Secret 32)) }
}
if (-not (Test-Path '.local/dev/environment')) {
    [IO.File]::WriteAllText((Join-Path $PWD '.local/dev/environment'), ('POSTGRES_PASSWORD=' + (New-Secret 36).TrimEnd('=') + "`n"))
}
if ($env:OS -eq 'Windows_NT') {
    $account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls '.local/dev' /inheritance:r /grant:r "${account}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Dateirechte der Entwicklungsgeheimnisse konnten nicht gesetzt werden.' }
}
if ($Action -eq 'prepare') { exit 0 }
& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Bitte Docker Desktop starten.' }
if ($Action -eq 'restart') {
    & docker @compose restart api worker
    if ($LASTEXITCODE -ne 0) { throw 'Neustart fehlgeschlagen.' }
}
# Build the base image without changing any regular containers or their data.
& docker build -t work-agent-api:latest ./backend
if ($LASTEXITCODE -ne 0) { throw 'Backend-Build fehlgeschlagen.' }
& docker @compose up -d --build --wait --wait-timeout 300
if ($LASTEXITCODE -ne 0) { throw 'Entwicklungsstart fehlgeschlagen. docker compose --env-file .local/dev/environment -f compose.dev.yaml logs' }
$state = Invoke-RestMethod 'http://localhost:5173/api/v1/auth/status'
Write-Host 'Entwicklung bereit: http://localhost:5173 (Demo, eigene Datenbank).'
if (-not $state.initialized) {
    $url = 'http://localhost:5173/#setup=' + [Uri]::EscapeDataString((Get-Content -Raw '.local/dev/secrets/setup_token').Trim())
    # The first-run token is kept out of checked-in launch settings and logs.
    # Opening the protected setup once stores it in sessionStorage in that tab.
    if (-not $NoBrowser) { Start-Process $url }
    Write-Host 'Ersteinrichtung: scripts/dev-setup.ps1 oeffnet den geschuetzten Einrichtungslink.'
}
