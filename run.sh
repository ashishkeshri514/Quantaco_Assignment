#!/usr/bin/env bash
# One-command local run: backend (8000) + frontend (5173)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BACKEND_PORT=8000
FRONTEND_PORT=5173

free_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "Freeing port $port (pids: $pids)"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 0.3
  fi
}

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r backend/requirements.txt

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

(
  cd backend
  python manage.py migrate --noinput
  python manage.py seed_demo
)

free_port "$BACKEND_PORT"
free_port "$FRONTEND_PORT"

cleanup() {
  echo ""
  echo "Stopping…"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Backend  → http://127.0.0.1:${BACKEND_PORT}"
echo "Frontend → http://127.0.0.1:${FRONTEND_PORT}"
echo "Login    → ops / ops1234"
echo ""

(
  cd backend
  python manage.py runserver "$BACKEND_PORT"
) &

(
  cd frontend
  npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
) &

wait
