$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$token = (Get-Content -Raw -LiteralPath (Join-Path $root '.local/dev/secrets/setup_token')).Trim()
Start-Process ('http://localhost:5173/#setup=' + [Uri]::EscapeDataString($token))
