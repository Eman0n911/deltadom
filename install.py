"""Install only prebuilt wheels in a folder-local environment. Bootstrap supports Python 3.9+."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def main():
    parser = argparse.ArgumentParser(description="安装并启动 DeltaDOM；不编译任何源码。")
    parser.add_argument("--install-only", action="store_true", help="安装并检查，不启动演示")
    parser.add_argument("--headless", action="store_true", help="在后台运行演示浏览器")
    parser.add_argument("--demo", choices=["demo", "binding-demo"], default="demo",
                        help="选择观察录制或点击身份检查演示")
    parser.add_argument("--output", default="deltadom-output/demo.json", help="结果文件位置")
    parser.add_argument("--env", type=Path, help="指定安装目录，默认当前包内 .deltadom-env")
    parser.add_argument("--install-browser", action="store_true", help="缺少浏览器时下载 Chromium")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    env = args.env.resolve() if args.env else root / ".deltadom-env"
    wheels = sorted((root / "wheels").glob("deltadom-*.whl")) or sorted(
        (root / "dist").glob("deltadom-*.whl")
    )
    if len(wheels) != 1:
        parser.exit(
            2, "没有找到唯一的预编译包。请使用带 wheels 文件夹的体验包，而不是纯源码压缩包。\n"
        )
    wheel = wheels[0]
    uv = shutil.which("uv")
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.exists():
            print("[1/3] 创建独立运行环境…", flush=True)
            if uv:
                run([uv, "venv", "--python", "3.12", env])
            elif sys.version_info >= (3, 12):  # noqa: UP036 -- bootstrap also runs on Python 3.9
                run([sys.executable, "-m", "venv", env])
            else:
                parser.exit(2, "需要 Python 3.12+ 或 uv（无需 Rust）。安装指引见 START_HERE.md。\n")
        print("[2/3] 安装已编译的程序…", flush=True)
        marker = env / ".deltadom-installed.json"
        identity = {
            "wheel": wheel.name,
            "size": wheel.stat().st_size,
            "mtime": wheel.stat().st_mtime_ns,
        }
        installed = json.loads(marker.read_text()) if marker.exists() else None
        if installed != identity:
            if uv:
                run(
                    [
                        uv,
                        "pip",
                        "install",
                        "--python",
                        python,
                        "--only-binary",
                        ":all:",
                        "--reinstall-package",
                        "deltadom",
                        wheel,
                    ]
                )
            else:
                run(
                    [
                        python,
                        "-m",
                        "pip",
                        "install",
                        "--only-binary=:all:",
                        "--force-reinstall",
                        wheel,
                    ]
                )
            marker.write_text(json.dumps(identity))
        print("[3/3] 检查浏览器…", flush=True)
        health = subprocess.run(
            [str(python), "-m", "deltadom.cli", "doctor"],
            capture_output=True,
            text=True,
            check=False,
        )
        if health.returncode:
            if args.install_browser:
                run([python, "-m", "playwright", "install", "chromium"])
                run([python, "-m", "deltadom.cli", "doctor"])
            else:
                print(health.stderr, file=sys.stderr)
                print(
                    "也可再次运行安装器并加 --install-browser，下载专用演示浏览器。",
                    file=sys.stderr,
                )
                return 2
        else:
            print(health.stdout.strip())
        if args.install_only:
            print("安装完成。重新运行此启动器即可观看浏览器演示。")
            return 0
        command = [python, "-m", "deltadom.cli", args.demo, "--output", args.output]
        if args.headless:
            command.append("--headless")
        run(command)
    except subprocess.CalledProcessError as exc:
        print("启动未完成。请查看上面的错误，或参考 START_HERE.md 中的常见问题。", file=sys.stderr)
        return exc.returncode
    except KeyboardInterrupt:
        print("\nDeltaDOM 已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
