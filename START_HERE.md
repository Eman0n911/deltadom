# 第一次运行 DeltaDOM

> 仓库现为私密研发状态，下载入口需要仓库访问权限。本说明保留给已获得 0.4 体验包的使用者；不是重新公开发布通知。

你会看到一个真实浏览器完成 8 步操作，终端同步显示每一步产生的内容量和校验结果。无需模型账号、API Key，也不用写代码。

## 准备好这三样

- **Apple 芯片 Mac**：在苹果菜单 →「关于本机」查看芯片。目前提供的预览包仅适合 Apple M 系列。
- **Python 3.12 或更新版本**：可以从 [Python 官网](https://www.python.org/downloads/macos/) 安装。已有 [uv](https://docs.astral.sh/uv/getting-started/installation/) 也可以，安装器会用它准备 Python。
- **Google Chrome**：已有 Chrome 就不需要单独下载演示浏览器。演示使用独立会话，不读取你的日常浏览器登录态。

不需要 Rust、Node.js 或编译器。首次安装需要联网下载 Python 依赖；演示本身只访问本地样例页面。

## 解压，然后运行

1. 解压 `DeltaDOM-0.4.0-macosx_11_0_arm64.zip`。
2. 保留 `install.py`、`Start DeltaDOM.command` 和 `wheels/` 在同一个文件夹。
3. 双击 **Start DeltaDOM.command**。终端会创建独立环境、安装预编译程序、检查浏览器，然后开始演示。

若双击没有运行，在解压后的文件夹打开终端，输入：

```sh
python3 install.py
```

只有 uv、没有 `python3` 时：

```sh
uv run --no-project --python 3.12 --no-build install.py
```

源码 ZIP 不包含预编译 wheel。请从 [0.4 实验版 Releases](https://github.com/Eman0n911/deltadom/releases/tag/v0.4.0) 下载包含 wheels 的体验包。

## 看到什么算成功

浏览器打开商品列表后，会自动输入 Rust、加载两条详情、反转排序、选中第 7 件商品、添加商品并刷新。约十几秒后，终端出现：

```text
Verified 8/8: every frame reconstructs the captured nodes.
```

这表示八次读取都能重建出捕获的页面节点。它验证的是这次本地演示，不代表真实模型任务的成功率。

结果保存在运行目录的 `deltadom-output/`：

| 文件 | 用途 |
|---|---|
| `demo.txt` | 易读的终端运行记录 |
| `demo.png` | 实际页面截图 |
| `demo.json` | 每步的完整技术记录，排查问题时使用 |
| `demo.ddt` | 可校验、可离线恢复的页面记录 |

无需激活环境，在解压目录中检查和比较：

```sh
python3 run.py replay deltadom-output/demo.ddt
python3 run.py diff deltadom-output/demo.ddt --before 2 --after 3
python3 run.py replay deltadom-output/demo.ddt --step 3 --output step-3.json
```

要录制自己的页面：`python3 run.py record https://example.com --output example.ddt`。打开的独立窗口可以手动操作，默认录制 20 次；页面内容写入本地，分享前请检查隐私。[更多录制说明](https://github.com/Eman0n911/deltadom/blob/main/docs/RECORDING.md)。

再次双击启动器即可重跑；相同安装包会复用已有环境。再次运行会覆盖同名 JSON/PNG/TXT，已有 DDT 录制会保留并另存新文件，要保留旧结果请先复制文件，或指定新输出位置：

```sh
python3 install.py --output second-run/demo.json
```

## 常见安装问题

**提示需要 Python 3.12+**

系统自带 Python 可能较旧。安装上面链接的新版 Python，重新打开终端再运行。也可以安装 uv，由安装器准备兼容版本。

**找不到浏览器**

安装 Chrome 后重试，或者让安装器下载专用 Chromium（需要联网）：

```sh
python3 install.py --install-browser
```

**提示 wheel 不适用于当前平台**

确认芯片是 Apple M 系列，且使用 Python 3.12+。Intel Mac、Windows 和 Linux 不能使用这份 Mac arm64 包。

**macOS 拦截双击启动**

可以在文件夹中用上面的 `python3 install.py` 命令启动。不需要关闭系统安全设置。本地预览包尚未签名或公证。

**依赖下载失败**

确认能联网访问 Python 包索引后重试同一命令。已安装的环境会保留，无需删除整个目录。

**只安装，不立即演示**

```sh
python3 install.py --install-only
```

**不显示浏览器窗口**

```sh
python3 install.py --headless
```

## 停止与卸载

演示正常完成后自动关闭独立浏览器。运行中可以在终端按 `Control + C` 停止。

关闭程序后，删除解压文件夹即可移除程序及其中的 `.deltadom-env`。你的 Chrome、Python、uv 不会被卸载；用 `--env` 或 `--output` 指定的其他目录需要自行保留或删除。通过 Playwright 另外下载的浏览器缓存也不随此文件夹删除。
