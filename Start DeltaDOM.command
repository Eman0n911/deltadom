#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 install.py "$@"
elif command -v uv >/dev/null 2>&1; then
  uv run --no-project --python 3.12 --no-build install.py "$@"
else
  echo '请先安装 Python 3.12+ 或 uv。安装说明在 START_HERE.md；不需要 Rust。'
  exit 2
fi
