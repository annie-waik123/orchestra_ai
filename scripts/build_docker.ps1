$ErrorActionPreference = "Stop"

# Resolve repository root path
$ROOT_DIR = Resolve-Path "$PSScriptRoot\.."

Write-Host "=== Building Sandbox Container Image ===" -ForegroundColor Cyan
docker build -t orchestra-sandbox -f "$ROOT_DIR\docker\sandbox\Dockerfile" "$ROOT_DIR"

Write-Host "=== Building API and Brain Services ===" -ForegroundColor Cyan
docker-compose -f "$ROOT_DIR\docker\compose\docker-compose.yml" build

Write-Host "=== Starting Orchestra AI Stack via Docker Compose ===" -ForegroundColor Cyan
docker-compose -f "$ROOT_DIR\docker\compose\docker-compose.yml" up -d

Write-Host "=== Orchestra AI Stack Started Successfully ===" -ForegroundColor Green
