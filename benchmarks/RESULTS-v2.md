# 0.3.0 修复与复测

**已修复操作缺口，尚未实现通用领先。** 自建动态商品列表出现有限的输出优势；公开页面开发集和未调优页面仍落后。原始 0.2.0 结果保留在 [首轮报告](README.md)。

## 改了什么

- 自定义点击元素：捕获 `cursor:pointer`、`onclick` 属性/函数提示，保留没有文字的 CSS 图标及其真实类名。原邮件条目和返回图标不再漏识别。并非完整事件监听器枚举，没有这些线索的监听器仍可能遗漏；继承 pointer 样式可能增加候选。
- 序列化：全量使用嵌套树表达父子与位置；重复结构确实更短时才使用表格。差分按 ID 发送变化字段，属性删除显式编码。没有删掉捕获节点、文字或属性来缩短输出。
- 可验证文本：新增 `TextMirror`，仅凭实际发送文本重建节点；不借用结构化 frame 中的隐藏全量数据。结构化协议仍为 v1，文本格式升级为 v2。
- 环境兼容：128 位随机 document 标识使用 `crypto.getRandomValues`，解决 HTTP/about:blank 上没有 `crypto.randomUUID` 的失败。

试过直接复用历史 quiet 状态以减少等待，但它会漏掉刚启动的定时更新。原有 timer-churn 测试失败，因此撤回该优化，默认每次仍保留 60 ms 稳定窗口。[拒绝记录](../artifacts/benchmarks/revision-v2/rejected-fast-settle.txt)已保存。

## 同口径 live 对比

固定协议见 [PROTOCOL-v2.md](PROTOCOL-v2.md)。开发集仍是四类 MiniWoB 页面、三个 seed、72 个状态；商品列表单列 24 个状态。新增集为 enter-password、click-tab、click-option，seed 44/55/66，共 54 个状态。新增集未用于候选调优；观察后没有再改核心。仍是固定动作生成页面状态，不是模型任务分数。

| 新输出 token 合计 | 0.2.0 DeltaDOM | 0.3.0 DeltaDOM | agent-browser 增量 | Browser Use DOM |
|---|---:|---:|---:|---:|
| MiniWoB 开发页面 | 36,475 | 24,072 | 12,320 | 19,292 |
| 自建商品列表 | 25,176 | 17,736 | 20,037 | 20,376 |
| 新增未调优页面 | 未运行 | 11,958 | 6,798 | 7,627 |

0.3 相对 0.2 的新输出下降 34.0%（开发页面）和 29.6%（商品列表）。商品列表较 agent-browser 原生增量少 **11.5%**；但开发页面仍为它的 **1.95 倍**，新增页面仍为 **1.76 倍**。这是 tokenizer 代理指标，不是模型实际费用。各工具的信息范围不同，不能从更短直接推出任务效果更好。

| 观察调用 p50（ms） | 0.3 DeltaDOM | agent-browser 增量 | Browser Use DomService |
|---|---:|---:|---:|
| MiniWoB 开发页面 | 74.50 | 34.62 | 5.56 |
| 自建商品列表 | 83.35 | 35.62 | 14.96 |
| 新增未调优页面 | 73.55 | 34.20 | 5.50 |

尚无速度优势。DeltaDOM 开发页面 capture 中位数 2.83 ms、core_boundary 0.21 ms，默认稳定等待占主要部分。Browser Use 行不含完整 Agent step；agent-browser 包含 CLI/daemon 往返。不同边界不作纯核心速度或端到端提速归因。

900 次捕获无错误、页面捕获前后无变化。300 次 DeltaDOM 状态同时通过结构化重建和仅文本重建；旧开发轨迹中待执行的 selector 均被捕获并标为可交互。原始记录：[开发集](../artifacts/benchmarks/observation-v2)、[新增集](../artifacts/benchmarks/holdout-v2)。

## 编码与感知变化的拆分

另将旧版的 96 个冻结节点快照原封不动送入新编码器：开发页面 36,475 → 19,340 token（下降 47.0%），商品列表 25,176 → 17,907（下降 28.9%），全部仅文本重建一致。这才是内容完全相同的编码比较，见 [serialization-v2](../artifacts/benchmarks/serialization-v2)。

live 结果还包含更多点击候选、空图标属性及新的 document 标识格式，所以不能把 live 全部差异归因于编码。序列化收益不会自动变成模型输入费用收益；模型仍需要历史、固定工具说明及 API/settle 等附加信息。

## 模型回归

使用 WorkBuddy UI 中标为 Deepseek-V4.1-Flash 的模型，新会话，继续采用旧试跑的 login-user / email-inbox、seed 11、每任务最多 8 动作、无视觉/evaluate 回退。唯一适配说明改为新文本格式的 `TEXT_GUIDE`。完整回复按原样保存后执行；模型费用及内部采样参数仍不可见。本次登录 3 步通过，邮件删除 1 步通过，均为原生 `done=true, raw_reward=1`。旧版邮件为点击被拒绝后放弃；新回复直接选择 class=trash 的节点 18。两个已知开发任务、每项一次，证明原失败得到修复，不能当成普遍成功率或优于其他模型的证据。人工/UI 墙钟时间不作速度比较。结果见 [workbuddy-v2](../artifacts/benchmarks/workbuddy-v2/results.json)。ChatGPT Desktop 三组仍未运行，未用 SpineCodex 替代。

## 验证与使用

- Rust 5 项测试，Python 20 项测试，clippy、ruff 通过。包含 300 次确定性节点变异、属性删除、重新挂载、丢帧、旧目标拒绝、定时更新、密码脱敏和真浏览器动作。
- 0.3.0 Mac arm64 wheel / ZIP 在空编译器 PATH 的干净环境安装通过，演示 8/8 步；重复安装也通过。[安装记录](../artifacts/installation-0.3.json)。
- 文本 v2 有格式变化；使用 [SDK 的 TextMirror/TEXT_GUIDE](../docs/SDK.md) 迁移手写旧文本解析器。
- 未发布 GitHub/PyPI；其他 OS/架构仍未安装验证。

同环境复现：

```sh
uv pip install --python .bench/venv/bin/python --only-binary=:all: dist/deltadom-0.3.0-cp312-abi3-macosx_11_0_arm64.whl
.bench/venv/bin/python benchmarks/observe_v2.py --output artifacts/benchmarks/new-development
.bench/venv/bin/python benchmarks/observe_v2.py --holdout --output artifacts/benchmarks/new-holdout
.bench/venv/bin/python benchmarks/summarize.py artifacts/benchmarks/new-development
.bench/venv/bin/python benchmarks/summarize.py artifacts/benchmarks/new-holdout
```

当前更合理的竞争方向和判定门槛见 [DIRECTION.md](../docs/DIRECTION.md)：为已有 actor 提供可重建状态更新，优先验证动态列表；用同模型、同动作循环和实际计费验证收益。原生 Browser Use 集成仍未完成，不能把方向写成已实现优势。
