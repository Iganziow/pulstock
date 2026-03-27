#!/usr/bin/env bash
# deploy.sh — Actualiza el backend de Pulstock en Hetzner
# Frontend se despliega automáticamente desde Vercel al hacer push a main
# Uso: ./deploy.sh [--no-migrate] [--no-build]
set -euo pipefail

COMPOSE="docker compose"
NO_MIGRATE=false
NO_BUILD=false

for arg in "$@"; do
  case $arg in
    --no-migrate) NO_MIGRATE=true ;;
    --no-build)   NO_BUILD=true ;;
  esac
done

echo "▶ [1/5] Pulling latest code..."
git pull origin main

if [ "$NO_BUILD" = false ]; then
  echo "▶ [2/5] Building API image..."
  $COMPOSE build --no-cache api celery-worker celery-beat
else
  echo "▶ [2/5] Skipping build (--no-build)"
fi

if [ "$NO_MIGRATE" = false ]; then
  echo "▶ [3/5] Running migrations..."
  $COMPOSE run --rm api python manage.py migrate --noinput
else
  echo "▶ [3/5] Skipping migrations (--no-migrate)"
fi

echo "▶ [4/5] Restarting services..."
$COMPOSE up -d --remove-orphans

echo "▶ [5/5] Health check..."
sleep 5
STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://api.pulstock.cl/api/health/ || true)
if [ "$STATUS" = "200" ]; then
  echo "✓ Deploy exitoso — API responde OK"
else
  echo "⚠ Health check retornó HTTP $STATUS — revisa los logs:"
  echo "  docker compose logs api --tail=50"
  exit 1
fi
