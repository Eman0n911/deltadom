# 0.4.0 发布前验证

已完成本地 Apple Silicon Mac 验证，未将其他平台构建配置当作安装验证。

| 检查 | 结果 | 证据 |
|---|---|---|
| Rust 单元测试 | 5 通过 | [日志](../artifacts/rust-tests-0.4.txt) |
| Python / 真实浏览器测试 | 29 通过 | [日志](../artifacts/tests-0.4-final.txt) |
| Ruff / cargo fmt / Clippy | 通过 | [Clippy](../artifacts/clippy-0.4.txt) |
| 最终 ZIP 首次及重复免编译安装 | 通过；PATH 无 Rust/Node/编译器 | [安装报告](../artifacts/installation-0.4-final.json) |
| 安装包内 `run.py --version` | DeltaDOM 0.4.0 | 同上 |
| 安装后 8 步演示 + DDT 校验 + 字段比较 | 通过 | 同上 |
| CLI 离线导出/比较 | 通过 | [回放](../artifacts/demo-replay-0.4.json)、[差分](../artifacts/demo-diff-0.4.json) |
| 同源快照恢复 | 450/450 逐字一致 | [逐段结果](../artifacts/benchmarks/recording-release/results.json) |
| Browser Use 原生 Agent 回调 | 输入逐字段一致；脚本响应器 | [接口结果](../artifacts/benchmarks/native-agent-contract/results.json) |

覆盖损坏字节、逐字节截断、缺失结束标记、限制解压输出、已有文件保护、空状态、全量回退、检查点、中文文本、刷新后的节点 ID 复用、中断前缀恢复，以及 API/稳定性警告的比较。原 0.3 的 300 次节点变更与过期操作回归继续通过。

没做的测试：ChatGPT Desktop 三个模型的自主任务、正式 WebArena/BrowserGym 分数、provider 缓存和真实费用、签名/公证、下载隔离属性下 Finder 双击、其他平台体验包安装。原 WorkBuddy 试跑只作为已发生缺陷的回归证据。

发布定位：实验版可校验观察记录工具。流式记录的体积优势不能替代上述尚缺的模型效能证据。公共日志只对工作站路径做脱敏；本地原件保留，见 PUBLIC_EXPORT.json。原 0.3 核心源文件另存 `evidence/source-0.3.0.tar.gz`，不公开整个开发历史。

GitHub 云端 CI：未运行。当前发布凭据缺少 workflow scope，CI 配置以 `ci/check.yml` 模板提供，未启用；未扩大凭据权限。
