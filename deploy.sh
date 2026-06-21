#!/usr/bin/env bash
# deploy.sh — Deploy de producción de Pulstock (TODO en un servidor Hetzner).
#
# Esta es la copia VERSIONADA del script que vive en el server como
# /home/ignacio/deploy.sh (aliases: pdeploy / pdeploy-api / pdeploy-web).
# Se ejecuta EN el servidor, no en local. Ver DEPLOY.md y docs/ops/04-deploy.md.
#
# NO usamos Vercel ni Docker para servir:
#   - Frontend Next.js → `next start` bajo PM2 (proceso `pulstock-web`, puerto 3000)
#   - Backend Django   → gunicorn nativo (puerto 8000)
#   - Nginx            → reverse proxy + SSL
# (arquitectura completa en docs/ops/02-arquitectura.md)
#
# IMPORTANTE: `git pull` NO actualiza el frontend por sí solo — el frontend
# sólo cambia con `next build` + restart de PM2 (modo `web` o `all`).
#
# Uso (en el server):
#   bash deploy.sh         # deploy normal (pull main + backend + frontend)
#   bash deploy.sh api     # solo backend  (~10s: migrate + reload gunicorn)
#   bash deploy.sh web     # solo frontend (~1-2min: next build + restart pm2)
#
# Workarounds que incluye:
#   - Maneja archivos owned por root con sudo chown.
#   - Restaura el 0018_merge_*.py local si fue eliminado por el pull.
#   - Mata el next-server huérfano antes de pm2 restart (sino EADDRINUSE loop).
#   - Verifica todo al final con curls.
#
# Idempotente: corre dos veces seguidas y nada se rompe.

set -e  # falla si cualquier comando falla
set -o pipefail

REPO=/var/www/pulstock
COLOR_OK='\e[32m'
COLOR_ERR='\e[31m'
COLOR_INFO='\e[36m'
COLOR_RESET='\e[0m'

log() { echo -e "${COLOR_INFO}>>>${COLOR_RESET} $*"; }
ok()  { echo -e "${COLOR_OK}✓${COLOR_RESET} $*"; }
err() { echo -e "${COLOR_ERR}✗${COLOR_RESET} $*" >&2; }

MODE="${1:-all}"
case "$MODE" in
  all|api|web) ;;
  *) err "Modo inválido: $MODE. Usa: all | api | web"; exit 1 ;;
esac

log "Modo: $MODE"

# ─── 1. Asegurar que ignacio puede operar el repo ────────────────
log "Asegurando ownership del repo a ignacio…"
if find $REPO -not -user ignacio -print -quit | grep -q .; then
  sudo chown -R ignacio:ignacio $REPO
  ok "chown OK"
else
  ok "ownership ya correcto"
fi

# ─── 2. Pull main ────────────────────────────────────────────────
log "Git pull origin main…"
cd $REPO
git fetch origin --prune
# Asegurar branch main
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
  log "Branch actual: $CURRENT_BRANCH — cambiando a main"
  git checkout main
fi
# Si hay archivo 0018_merge fuera del git, evitar conflicto
if [ -f apps/api/core/migrations/0018_merge_0017_cronheartbeat_0017_merge_20260405_1600.py ]; then
  if ! git ls-files --error-unmatch apps/api/core/migrations/0018_merge_0017_cronheartbeat_0017_merge_20260405_1600.py 2>/dev/null; then
    rm apps/api/core/migrations/0018_merge_0017_cronheartbeat_0017_merge_20260405_1600.py
  fi
fi
git pull origin main
ok "Pull OK — HEAD: $(git log --oneline -1)"

# ─── 3. Recrear merge migration local (evita conflicto huérfanos) ─
MERGE_FILE=apps/api/core/migrations/0018_merge_0017_cronheartbeat_0017_merge_20260405_1600.py
if [ ! -f "$MERGE_FILE" ]; then
  log "Recreando $MERGE_FILE (untracked, evita conflicto huérfanos)…"
  cat > "$MERGE_FILE" <<'MERGE_EOF'
# Merge migration restaurado localmente — NO COMMITEAR.
# Ver docs/ops/04-deploy.md.
from django.db import migrations
class Migration(migrations.Migration):
    dependencies = [('core', '0017_cronheartbeat'), ('core', '0017_merge_20260405_1600')]
    operations = []
MERGE_EOF
  ok "recreado"
fi

# ─── 4. Backend deploy ───────────────────────────────────────────
if [ "$MODE" = "all" ] || [ "$MODE" = "api" ]; then
  log "Backend: migrate + reload gunicorn…"
  cd $REPO/apps/api
  source venv/bin/activate
  python manage.py migrate
  GUNICORN_PID=$(pgrep -f 'gunicorn.*api.wsgi' -o)
  if [ -n "$GUNICORN_PID" ]; then
    sudo kill -HUP "$GUNICORN_PID"
    ok "gunicorn HUP enviado a PID $GUNICORN_PID"
  else
    err "gunicorn no está corriendo — revisar manualmente"
  fi
fi

# ─── 5. Frontend deploy ──────────────────────────────────────────
if [ "$MODE" = "all" ] || [ "$MODE" = "web" ]; then
  log "Frontend: build…"
  cd $REPO/apps/web
  npx next build > /tmp/next-build.log 2>&1 && ok "next build OK" || {
    err "next build falló — revisar /tmp/next-build.log"
    tail -30 /tmp/next-build.log
    exit 1
  }

  log "Stop pm2 + matar next-server huérfanos + start pm2…"
  sudo pm2 stop pulstock-web || true
  sudo pkill -KILL -f 'next-server' 2>/dev/null || true
  sudo pkill -KILL -f 'next start' 2>/dev/null || true
  sleep 2
  if sudo ss -tlnp 2>/dev/null | grep -q ':3000'; then
    err "Puerto 3000 sigue ocupado — investigar manualmente"
    sudo ss -tlnp | grep :3000
    exit 1
  fi
  sudo pm2 start pulstock-web
  sleep 8
  if sudo pm2 jlist 2>/dev/null | python3 -c "import json,sys; p=json.load(sys.stdin)[0]; sys.exit(0 if p['pm2_env']['status']=='online' else 1)"; then
    ok "pm2 pulstock-web online"
  else
    err "pm2 pulstock-web NO está online — revisar 'sudo pm2 logs pulstock-web'"
    exit 1
  fi
fi

# ─── 6. Verificación final ───────────────────────────────────────
log "Verificación final…"
HTTP=$(timeout 8 curl -sk -o /dev/null -w '%{http_code}' https://pulstock.cl 2>&1 || echo TIMEOUT)
[ "$HTTP" = "200" ] && ok "pulstock.cl → 200" || err "pulstock.cl → $HTTP"

HTTP=$(timeout 8 curl -sk -o /dev/null -w '%{http_code}' https://api.pulstock.cl/api/core/health/ 2>&1 || echo TIMEOUT)
[ "$HTTP" = "200" ] && ok "api.pulstock.cl/health → 200" || err "api.pulstock.cl/health → $HTTP"

HTTP=$(timeout 8 curl -sk -o /dev/null -w '%{http_code}' -X POST https://api.pulstock.cl/api/printing/print/ 2>&1 || echo TIMEOUT)
[ "$HTTP" = "401" ] && ok "/api/printing/print/ → 401 (auth requerido — OK)" || err "/api/printing/print/ → $HTTP (esperado 401)"

echo
ok "=== DEPLOY $MODE COMPLETO ==="
