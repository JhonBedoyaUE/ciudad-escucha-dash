#!/usr/bin/env bash
# Publica la versión de master en el servidor AWS (aws-sia).
#
#   ./deploy/actualizar-aws.sh
#
# El servidor tiene:
#   - /opt/ciudad-escucha        clon de este repo
#   - ciudad-escucha.service     app Waitress en el puerto 8505 (systemd)
#   - cloudflared-ciudad-escucha.service  túnel de Cloudflare hacia 8505
set -euo pipefail
HOST="${HOST:-aws-sia}"
RUTA="${RUTA:-/opt/ciudad-escucha}"

echo "→ actualizando $HOST:$RUTA"
ssh "$HOST" "set -e
  cd $RUTA
  git pull --ff-only --quiet
  echo '  commit: '\$(git log --oneline -1)
  sudo systemctl restart ciudad-escucha
  sleep 4
  systemctl is-active ciudad-escucha
  curl -s -o /dev/null -w '  health local: %{http_code}\n' http://127.0.0.1:8505/health
"
echo "→ comprobando el dominio público"
curl -s -o /dev/null -w "  https://c-escucha.jhonb.dev/ -> %{http_code}\n" --max-time 20 https://c-escucha.jhonb.dev/
