#!/usr/bin/env bash
# Arranque de CIUDAD ESCUCHA (Dash) con servidor de producción
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8505}"

if [ ! -d venv ]; then
  python -m venv venv
  ./venv/bin/pip install -q --upgrade pip
  ./venv/bin/pip install -q -r requirements.txt
fi

echo "🚀 Dashboard Ciudad Escucha (Dash) → http://localhost:${PORT}"

exec ./venv/bin/python - <<PYEOF
import socket

from waitress import serve
from app import app


@app.server.route("/health")
def health():
    return "ok", 200


def sockets_duales(port):
    """Abre IPv4 e IPv6 a la vez.

    Cloudflare Tunnel apunta a \`http://localhost:${PORT}\` y en este equipo
    \`localhost\` resuelve primero a ::1; con host="0.0.0.0" (solo IPv4) el
    túnel respondía 502. Con estos dos sockets el servicio entra por ambos.
    """
    socks = []
    for familia, direccion in ((socket.AF_INET, ("0.0.0.0", port)),
                               (socket.AF_INET6, ("::", port))):
        try:
            s = socket.socket(familia, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if familia == socket.AF_INET6:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            s.bind(direccion)
            socks.append(s)
        except OSError as exc:
            print(f"⚠️  {familia} no disponible en el puerto {port}: {exc}")
    if not socks:
        raise SystemExit(f"No se pudo abrir el puerto {port}")
    return socks


serve(app.server, sockets=sockets_duales(int("${PORT}")), threads=8)
PYEOF
