"""Small CLI: watch a real browser run, or check the installation."""

import argparse
import asyncio
import json
import sys
from importlib.metadata import version

from playwright.async_api import Error as PlaywrightError

from .demo import run
from .recording import diff_tape, inspect_tape, record_page
from .runtime import BrowserUnavailable, inspect_browser


def main():
    parser = argparse.ArgumentParser(
        prog="deltadom", description="Compact browser observations. 首次体验：deltadom demo"
    )
    parser.add_argument("--version", action="version", version=f"DeltaDOM {version('deltadom')}")
    commands = parser.add_subparsers(dest="command")
    demo = commands.add_parser("demo", aliases=["start"], help="观看真实浏览器完成 8 步本地演示")
    demo.add_argument("--headless", action="store_true", help="在后台运行浏览器")
    demo.add_argument("--channel", choices=["auto", "chrome", "chromium"], default="auto")
    demo.add_argument("--output", default="deltadom-output/demo.json", help="JSON 结果保存位置")
    demo.add_argument(
        "--delay", type=float, default=None, help="每步停留秒数，默认 1.2；后台默认 0"
    )
    demo.add_argument("--keep-open", action="store_true", help="结束后按回车关闭浏览器")
    demo.add_argument("--tokens", action="store_true", help="额外测量 token（需安装 tiktoken）")
    doctor = commands.add_parser("doctor", help="检查原生扩展和浏览器")
    doctor.add_argument("--json", action="store_true")
    record = commands.add_parser("record", help="打开网页并录制观察；录制期间可手动操作")
    record.add_argument("url")
    record.add_argument("--output", default="recording.ddt")
    record.add_argument("--count", type=int, default=20)
    record.add_argument("--interval", type=float, default=1.0)
    record.add_argument("--channel", choices=["auto", "chrome", "chromium"], default="auto")
    record.add_argument("--headless", action="store_true")
    replay = commands.add_parser("replay", help="离线检查录制完整性，可导出指定步骤")
    replay.add_argument("file")
    replay.add_argument("--step", type=int)
    replay.add_argument("--output")
    replay.add_argument(
        "--recover", action="store_true", help="仅恢复中断录制的完整前缀，不忽略损坏"
    )
    diff = commands.add_parser("diff", help="查看录制中两步之间的变化")
    diff.add_argument("file")
    diff.add_argument("--before", type=int, required=True)
    diff.add_argument("--after", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.command == "record":
            print("录制到本地文件；页面文字和表单内容可能包含隐私，请勿直接公开记录。")
            asyncio.run(
                record_page(
                    args.url,
                    args.output,
                    count=args.count,
                    interval=args.interval,
                    channel=args.channel,
                    headless=args.headless,
                )
            )
        elif args.command == "replay":
            print(
                json.dumps(
                    inspect_tape(
                        args.file, step=args.step, output=args.output, recover=args.recover
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "diff":
            print(
                json.dumps(
                    diff_tape(args.file, args.before, args.after), ensure_ascii=False, indent=2
                )
            )
        elif args.command == "doctor":
            report = asyncio.run(inspect_browser())
            if args.json:
                print(json.dumps(report, ensure_ascii=False))
            else:
                print(
                    f"DeltaDOM ready | Python {report['python']} | {report['channel']} {report['browser']}"
                )
                print("下一步：deltadom demo")
        elif args.command in {"demo", "start"}:
            delay = args.delay if args.delay is not None else (0 if args.headless else 1.2)
            if not 0 <= delay <= 60:
                parser.error("--delay 必须在 0–60 秒之间")
            asyncio.run(
                run(
                    args.channel,
                    args.output,
                    not args.headless,
                    delay=delay,
                    tokens=args.tokens,
                    keep_open=args.keep_open,
                )
            )
        else:
            parser.print_help()
    except (BrowserUnavailable, PlaywrightError, OSError, ValueError) as exc:
        print(f"操作未完成：{exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        print("\nDeltaDOM 已停止。")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
