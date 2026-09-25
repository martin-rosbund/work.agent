param([string]$SkillsRoot)
$ErrorActionPreference = 'Stop'
$source = Join-Path (Split-Path -Parent $PSScriptRoot) 'skills/github-issue-fix'
if (-not $SkillsRoot) {
    $codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $SkillsRoot = Join-Path $codexRoot 'skills'
}
$root = [IO.Path]::GetFullPath($SkillsRoot)
$target = [IO.Path]::GetFullPath((Join-Path $root 'github-issue-fix'))
if ([IO.Path]::GetDirectoryName($target) -ne $root.TrimEnd('\','/')) { throw 'Ungueltiges Skill-Ziel.' }
New-Item -ItemType Directory -Force -Path $target | Out-Null
# Copy only this maintained skill; never enumerate/delete other installed skills.
foreach ($relative in @('SKILL.md', 'agents/openai.yaml', 'scripts/issue_workflow.py')) {
    $destination = Join-Path $target $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath (Join-Path $source $relative) -Destination $destination -Force
}
Write-Host "Skill installiert: $target"
Write-Host 'Automatische Auswahl bleibt aktiv; expliziter Aufruf: $github-issue-fix'
