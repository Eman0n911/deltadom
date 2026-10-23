# 更新记录

## 0.5.0.dev9 — private local preview, 2026-10-23

- Add automatic visible record binding and trusted input propagation checks.
- Add Option/Alt target selection, single bound-click replay, and a local browser demo.
- Preserve all fixed benchmark outcomes, including baseline role corrections and failed candidates.
- Verify prebuilt Mac arm64 installation in a fresh directory. No publication.


## 0.4.0 — checked recordings (experimental)

- Add `record`, `replay`, `diff`, explicit interrupted-prefix recovery, and a folder-local `run.py` launcher.
- Add DDT1 streamed recordings with bounded decode, adaptive previous-state dictionary, full checkpoints, per-record checks and end seal. Ordinary whole-session gzip remains the smaller offline archival option in measured cases.
- Add opt-in Browser Use 0.13.11 step recording without changing the actor's inputs/actions. This is not model acceleration or complete provider request logging.
- Fix stale CLI version reporting and receiver acceptance of duplicate IDs/sibling positions; preserve state after rejection.
- Include local demo recording and native dependency license notices in distributable wheels.
- Preserve the 0.3 negative performance results and raw synthetic evidence. Publish no general task success or cost advantage claim.


## 0.3.0 — 本地修复预览，2026-10-22

- 修复有 pointer/onclick 线索的自定义点击元素与空 CSS 图标遗漏。
- 使用不依赖安全上下文的 128 位随机 document 标识，支持 HTTP/about:blank。
- 文本 v2：嵌套树、字段/属性差分和按字节择优的重复结构表；结构化协议仍为 v1。新增 TextMirror 与 TEXT_GUIDE。
- 保留默认稳定窗口；拒绝了会漏定时更新的提前返回候选。
- 记录 900 次新观察和独立文本重建；胜出范围与未胜出范围见 [复测报告](benchmarks/RESULTS-v2.md)。
- 文本格式有变更，手写旧文本解析器须迁移；浏览器捕获覆盖限制仍在。


## 0.2.0 — 本地预览，2026-10-22

- 新增 `deltadom demo`：观看真实浏览器完成 8 步操作，终端显示逐步字节量与重建校验。
- 新增 `deltadom doctor`：检查原生扩展和浏览器；自动尝试 Chromium 与系统 Chrome。
- 默认演示无需 tokenizer，不访问模型，保存 JSON、真实截图和终端记录。
- 新增只接受预编译 wheel 的安装器与 macOS 双击启动器。
- 按“用途 → 演示 → 安装 → Python 接入”重写中英文 README，补充安装排错与可运行示例。
- 撤下 HTML 体验台，旧实现保存在本地 `archive/html-playground` 分支。

状态：Apple 芯片 Mac 本地预览；尚未发布。Browser Use 原生集成仍未实现。

## 0.1.0 — 本地 MVP，2026-10-22

Rust/PyO3 结构压缩、可重建差分、稳定节点动作、显式 API 字段投影，以及本地 8 步命令行演示。
