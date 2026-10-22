# 0.2 本地预览验证

日期：2026-10-22。验证范围：免编译安装 → 真实浏览器演示 → 结果文件。展示入口已从 HTML 控制台改为 README、命令行和真实浏览器；旧实现留在本地 `archive/html-playground` 分支。

## 已验证

| 检查 | 结果 |
|---|---|
| Rust 核心 `cargo test --locked` | 5 passed |
| 既有 Python 核心与浏览器测试 | 10 passed |
| 新增演示导出与 CLI 参数检查 | 修复导出类型问题后，4 passed |
| `cargo clippy --all-targets -- -D warnings` | 通过 |
| `ruff check python tests examples install.py scripts` | 通过 |
| `examples/observe.py` | 真浏览器填表；304 个语义节点重建一致 |
| 最终 ZIP 全新安装 | 通过；路径含空格，独立虚拟环境，PATH 无编译工具 |
| 同一 ZIP 第二次安装 | 通过，复用环境与安装标记 |
| 纯安装环境运行 demo | 8 步通过；未安装 tiktoken 或其他开发依赖 |
| 通过打包启动器运行可见浏览器 | 8 步通过；自动发现系统 Chrome，生成 JSON、PNG、TXT |
| wheel 内容检查 | 包含原生扩展和样例页；不包含旧 studio/web 控制台 |

安装报告：[installation.json](../artifacts/installation.json)。记录最终 ZIP 的 SHA-256、两次安装输出、实际安装路径、Python 与浏览器版本、运行结果。验证时 PATH 中 `cargo`、`rustc`、`cc`、`clang`、`node`、`uv` 均不可用；安装命令强制 `--only-binary=:all:`。这是免编译安装证据，不是无需 Python 的独立桌面程序。

可见浏览器演示：[终端记录](../artifacts/preview-demo.txt)、[原始 JSON](../artifacts/preview-demo.json)、[页面截图](../artifacts/preview-demo.png)。运行的是打包后的启动脚本，未测试 Finder 双击、下载隔离属性或公证流程。

## 复现

开发环境构建：

```sh
maturin build --release --locked --out dist
python scripts/package_preview.py dist/deltadom-0.2.0-cp312-abi3-macosx_11_0_arm64.whl
python scripts/verify_preview.py dist/DeltaDOM-0.2.0-macosx_11_0_arm64.zip
```

终端运行预览包（从解压目录）：

```sh
sh './Start DeltaDOM.command'
```

只做后台验证可用 `python3 install.py --headless`。

## 演示测量口径

固定 30 商品样例，8 步：首次读取、未变化、填表、API、反转排序、选中商品、新增、同地址刷新。每步把差分应用到 StateMirror，再与当前捕获的节点逐字段比较；没有用预写结果代替捕获。

- `FULL BYTES`：当前语义节点的完整 JSON 的 UTF-8 字节数。
- `SENT BYTES`：本次新生成的 DOM 文本字节数，未实际发送给模型。不含 API、等待信息或历史上下文。
- 完整 observation 字节量、每步计时与接口数据保存在 JSON 中。
- 默认不加载 tokenizer。可选 `--tokens` 需要额外安装 tiktoken；首次获取 tokenizer 可能联网。早期 token 实验保留在 [VALIDATION.md](VALIDATION.md)，不冒充本轮结果。

## 发现并修复

首次新增导出测试失败：API 与 warnings 在内存中为 tuple，JSON 读取后为 list，因此返回结果和保存文件不完全相等。导出构造阶段统一转成 list，保留原验收断言；修复后受影响的 4 项测试全部通过。其余 10 项在该轮完整测试中通过。

## 未验证 / not_run

- Linux、Windows、Intel Mac 的安装与运行；CI 矩阵已准备，但未在线执行。
- Finder 双击及从公网下载后的 Gatekeeper 行为；包未签名、公证。
- Browser Use 原生接入、公平性能对比、真实站点任务集、LLM 成功率与计费成本。
- GitHub、PyPI 或其他公开发布；公开许可证尚待选择。
