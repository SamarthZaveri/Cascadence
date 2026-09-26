param([switch]$CollectData, [int]$CompanyLimit = 100)

# Run from PowerShell. Stops at every failed native command, including Docker.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.env')) { throw 'Create .env from .env.example and set your local credentials first.' }
if ($CompanyLimit -lt 1 -or $CompanyLimit -gt 500) { throw 'CompanyLimit must be 1-500.' }
function dc {
    & docker compose --env-file .env -f infra/docker-compose.yml @args
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed (exit $LASTEXITCODE). Stop and read the error above." }
}

dc stop celery_worker celery_beat
dc build backend frontend celery_worker celery_beat
dc up -d --wait postgres neo4j redis
New-Item -ItemType Directory -Force backups | Out-Null
$backup = 'backups/pre-phase4-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump'
dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/pre-phase4.dump'
dc cp postgres:/tmp/pre-phase4.dump $backup
dc run --rm --no-deps backend alembic upgrade head
dc up -d --wait backend frontend
dc exec -T backend python -m app.services.ingestion.cli cleanup-synthetic --apply
dc exec -T backend python -m app.services.extra_signals.cli bootstrap
dc exec -T backend python -m app.services.gnn.cli snapshot
dc exec -T backend pytest tests/api tests/services/test_phase4.py -q
if ($CollectData) {
    # Uses SEC contact User-Agent and the free GDELT endpoint. Downloads may take time.
    dc exec -T backend python -m app.services.ingestion.universe expand --limit $CompanyLimit
    dc exec -T backend python -m app.services.ingestion.universe ingest --limit $CompanyLimit --days 7
    dc exec -T backend python -m app.services.ingestion.universe topics --days 7
    dc exec -T backend python -m app.services.gnn.cli score
}
dc up -d --wait celery_worker celery_beat prometheus grafana
Invoke-RestMethod 'http://localhost:8000/health'
dc ps
Write-Host 'Phase 4 installed. Open http://localhost:3000/dashboard. Check Models & coverage.' -ForegroundColor Green
Write-Host "PostgreSQL backup: $backup"
