#!/usr/bin/env bash
#Arranque de CIUDAD ESCUCHA (Dash) con servidor de producción
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8050}"

if [ ! -d venv ]; then
  python -m venv venv
  ./venv/bin/pip install -q --upgrade pip
  ./venv/bin/pip install -q -r requirements.txt
fi

echo "🚀 Dashboard Ciudad Escucha (Dash) → http://localhost:${PORT}"
exec ./venv/bin/python - <<PYEOF
from waitress import serve
import os
from app import server, app
app._favicon = "🏙️"

@app.server.route("/health")
def health():
    return "ok", 200

serve(app.server, host="0.0.0.0", port=int("${PORT}"), threads=8)
PYEOF
