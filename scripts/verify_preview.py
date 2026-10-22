"""Exercise the shipped ZIP, with an empty PATH, outside the source checkout."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/installation.json"))
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="DeltaDOM clean install "))
    with zipfile.ZipFile(args.archive) as z:
        z.extractall(root)
    folder = next(p for p in root.iterdir() if p.is_dir())
    empty_path = root / "empty-path"
    empty_path.mkdir()
    env = dict(os.environ, PATH=str(empty_path), PYTHONPATH="", PYTHONNOUSERSITE="1")
    assert all(
        shutil.which(x, path=env["PATH"]) is None
        for x in ["cargo", "rustc", "cc", "clang", "node", "uv"]
    )
    commands = [sys.executable, str(folder / "install.py"), "--install-only"]
    first = subprocess.run(
        commands, cwd=folder, env=env, capture_output=True, text=True, timeout=180, check=False
    )
    if first.returncode:
        print(first.stdout + first.stderr)
        raise SystemExit(first.returncode)
    second = subprocess.run(
        commands, cwd=folder, env=env, capture_output=True, text=True, timeout=60, check=False
    )
    if second.returncode:
        print(second.stdout + second.stderr)
        raise SystemExit(second.returncode)
    python = folder / ".deltadom-env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Use only the installed wheel, without development dependencies or source checkout.
    smoke = r"""
import importlib.util,json,subprocess,sys
from pathlib import Path
from importlib.resources import files
assert importlib.util.find_spec('tiktoken') is None
subprocess.run([sys.executable,'-I','-m','deltadom.cli','demo','--headless','--output','result.json'],check=True)
result=json.loads(Path('result.json').read_text())
assert result['steps']==8 and result['reconstruction_equal']
assert [o['frame']['kind'] for o in result['observations']]==['full']+['delta']*6+['full']
assert result['observations'][1]['frame']['upsert']==[]
assert result['observations'][3]['api']
assert Path('result.png').is_file() and Path('result.txt').is_file()
from deltadom.recording import inspect_tape, diff_tape
assert inspect_tape(result['recording'])['snapshots'] == 8
assert diff_tape(result['recording'], 2, 3)['changed']
print(json.dumps({'module':str(files('deltadom')),'steps':result['steps'],'reconstruction_equal':result['reconstruction_equal'],'channel':result['channel'],'browser':result['browser'],'no_tokenizer_dependency':True,'json_screenshot_transcript':True}))
"""
    result = subprocess.run(
        [str(python), "-I", "-c", smoke],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        print(result.stdout + result.stderr)
        raise SystemExit(result.returncode)
    launcher_check = subprocess.run(
        [sys.executable, str(folder / "run.py"), "--version"],
        cwd=folder, env=env, capture_output=True, text=True, check=True, timeout=20,
    )
    assert launcher_check.stdout.strip() == "DeltaDOM 0.4.0"
    entry = zipfile.ZipFile(args.archive).getinfo(folder.name + "/Start DeltaDOM.command")
    executable = bool((entry.external_attr >> 16) & 0o111)
    assert executable
    # Paths in the report are local provenance, not a published install URL.
    report = {
        "status": "pass",
        "folder_launcher": launcher_check.stdout.strip(),
        "archive": args.archive.name,
        "archive_sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
        "compiler_tools_on_path": [],
        "install_directory": str(folder),
        "python": sys.version.split()[0],
        "first_install": first.stdout + first.stderr,
        "second_install": second.stdout + second.stderr,
        "packaged_demo": json.loads(result.stdout.strip().splitlines()[-1]),
        "launcher_executable_in_zip": executable,
        "dependencies_compiled": bool(
            re.search(r"Building wheel|Compiling", first.stdout + first.stderr)
        ),
    }
    assert not report["dependencies_compiled"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {"status": "pass", "report": str(args.output), "install_directory": str(folder)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
