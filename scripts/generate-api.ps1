$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$root = $PWD.Path
& docker run --rm --entrypoint python -v "${root}/backend:/app:ro" -v "${root}/contracts:/output" work-agent-api:latest scripts/export_openapi.py /output/openapi.json
if ($LASTEXITCODE -ne 0) { throw 'OpenAPI-Export fehlgeschlagen.' }
& docker run --rm -v "${root}/frontend:/app" -v /app/node_modules -v "${root}/contracts:/contracts:ro" -w /app node:22-bookworm-slim sh -c 'npm ci --ignore-scripts && npm run api:generate'
if ($LASTEXITCODE -ne 0) { throw 'TypeScript-Generierung fehlgeschlagen.' }
