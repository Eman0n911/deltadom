"""Run the folder-local installation without activating an environment (Python 3.9+)."""

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
python = root / ".deltadom-env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not python.exists():
    print("请先运行 python3 install.py；安装说明见 START_HERE.md。", file=sys.stderr)
    raise SystemExit(2)
raise SystemExit(subprocess.call([str(python), "-m", "deltadom.cli", *sys.argv[1:]]))
