$ErrorActionPreference = 'Stop'
$desktop = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
if (-not (Test-Path -LiteralPath $desktop)) { throw 'Docker Desktop wurde nicht gefunden.' }
$settings = Join-Path $env:APPDATA 'Docker/settings-store.json'
if (Test-Path -LiteralPath $settings) {
    $data = Get-Content -Raw -LiteralPath $settings | ConvertFrom-Json
    $data | Add-Member -NotePropertyName AutoStart -NotePropertyValue $true -Force
    [IO.File]::WriteAllText($settings, ($data | ConvertTo-Json -Depth 100))
}
# Use the per-user Windows startup registration, never a pre-login service.
$run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
New-ItemProperty -LiteralPath $run -Name 'Docker Desktop' -Value ('"' + $desktop + '"') -PropertyType String -Force | Out-Null
$approved = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
if (Test-Path -LiteralPath $approved) {
    New-ItemProperty -LiteralPath $approved -Name 'Docker Desktop' -PropertyType Binary -Value ([byte[]](2,0,0,0,0,0,0,0,0,0,0,0)) -Force | Out-Null
}
Write-Host 'Docker Desktop startet nach der naechsten Windows-Anmeldung. Laufende Container wurden nicht unterbrochen.'
