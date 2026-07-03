#!/bin/bash
set -e

# Resolve repository root
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Building Sandbox Container Image ==="
docker build -t orchestra-sandbox -f "$ROOT_DIR/docker/sandbox/Dockerfile" "$ROOT_DIR"

echo "=== Building API and Brain Services ==="
docker-compose -f "$ROOT_DIR/docker/compose/docker-compose.yml" build

echo "=== Starting Orchestra AI Stack via Docker Compose ==="
docker-compose -f "$ROOT_DIR/docker/compose/docker-compose.yml" up -d

echo "=== Orchestra AI Stack Started Successfully ==="
