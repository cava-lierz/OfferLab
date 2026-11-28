#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -gt 1 || ( $# -eq 1 && $1 != '--reload' ) ]]; then
  echo '用法：python3 scripts/manage.py dev [--reload]' >&2
  exit 2
fi
if [ ! -x .venv/bin/python ] || [ ! -f frontend/node_modules/vite/bin/vite.js ] || ! .venv/bin/python -c 'import fastapi, httpx, dotenv, multipart, pypdf' >/dev/null 2>&1; then
  bash scripts/setup.sh
elif [ ! -f .env ]; then
  (umask 077; cp -n .env.example .env)
fi
backend_pid=''
frontend_pid=''
cleanup() {
  trap - EXIT INT TERM
  if [ -n "$backend_pid" ]; then kill "$backend_pid" 2>/dev/null || true; fi
  if [ -n "$frontend_pid" ]; then kill "$frontend_pid" 2>/dev/null || true; fi
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 "$@" &
backend_pid=$!
(
  cd frontend
  exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort
) &
frontend_pid=$!
echo 'OfferLab: http://127.0.0.1:5173  |  API: http://127.0.0.1:8000/docs'
echo '按 Ctrl+C 同时停止前后端。'
wait -n "$backend_pid" "$frontend_pid"
