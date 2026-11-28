#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo '请先运行 python3 scripts/manage.py setup 安装依赖。' >&2
  exit 1
fi
.venv/bin/python -c 'import fastapi, httpx, dotenv, multipart, pypdf'
.venv/bin/python -m unittest discover -s tests -v
(
  cd frontend
  npm test
  npm run build
)
echo '后端测试与前端构建通过。真实 Gateway 接入请另运行 python3 scripts/manage.py gateway-check。'
