#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PIP_CACHE_DIR="$PWD/.cache/pip"
export npm_config_cache="$PWD/.cache/npm"
mkdir -p "$PIP_CACHE_DIR" "$npm_config_cache"
if ! command -v python3 >/dev/null || ! command -v npm >/dev/null; then
  echo '需要 Python 3.11+ 和 Node.js 22.12+（含 npm）。' >&2
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11+"'
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22 || (a===22 && b<12)) { console.error("需要 Node.js 22.12+"); process.exit(1) }'
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  if ! python3 -m venv .venv; then
    echo '无法创建虚拟环境。请先为系统 Python 安装 venv/ensurepip 支持（Ubuntu 通常为 python3-venv），然后重试。' >&2
    exit 1
  fi
fi
.venv/bin/python -m pip install -r backend/requirements.txt
(
  cd frontend
  if [ -f package-lock.json ]; then npm ci; else npm install; fi
)
if [ ! -f .env ]; then
  (umask 077; cp .env.example .env)
fi
echo '依赖安装完成。默认演示模式；运行 bash scripts/dev.sh 启动。'
