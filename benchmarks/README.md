**0.4 新增：[增量记录的同源比较与发布边界](RECORDING-RESULTS.md)。以下保留原观察层负结果。**

# DeltaDOM benchmarks

最新：[0.3.0 修复复测](RESULTS-v2.md)。以下保留 0.2.0 的首轮原始结果及口径。

先回答：**首轮 0.2.0 DeltaDOM 尚未胜过主流工具。** 本目录包含可复现的观察层对比、原始输出和小规模模型闭环测试入口。不会把输出更短当成任务成功，也不会把模型自述当成 evaluator 分数。

## 公开 benchmark 怎么选

| Benchmark | 对本项目的用途 | 运行门槛与口径 |
|---|---|---|
| [MiniWoB++](https://github.com/Farama-Foundation/miniwob-plusplus) | 第一层回归：表单、列表、事件监听、动态页面；容易定位感知与动作问题 | 本地页面可运行。正式任务必须保留原 evaluator、seed 和环境设置；本轮只用其页面做 replay 与受限 smoke，不是官方分数 |
| [WebArena-Verified](https://github.com/ServiceNow/webarena-verified) | 首选主评测：实际网站工作流、跨步骤状态、功能成功率 | 提供 812 个任务及 258-task Hard subset；确定性判定与网络 trace。在线任务仍需站点环境；离线 replay 评分不等于无需环境生成新轨迹 |
| [BrowserGym](https://github.com/ServiceNow/BrowserGym) | 统一环境接口，连接 MiniWoB、WebArena 等 | 它是评测环境框架，不是一个可以与所有任务混成同一分数的榜单 |
| [BU Bench V2.1](https://github.com/browser-use/benchmark) | 第二阶段对照：直接对齐 Browser Use 生态的真实网站任务 | 当前 200-task 数据集。必须固定 release、数据与 judge；旧 60-task 图表不可直接比较。真实网站、模型与 cloud 设置都会影响结果 |

建议顺序：先修 MiniWoB 回归发现的实际缺口；再做固定 WebArena-Verified pilot；最后扩大到其完整集与 BU Bench。不要先刷公开榜单再定义收益指标。

## 首轮观察层实测

2026-10-22，macOS arm64，Chrome 156.0.8078.47；三个独立浏览器进程。固定版本：DeltaDOM 0.2.0 / c4df334，Browser Use 0.13.11（本轮安装的 PyPI 版本），agent-browser 0.39.1，Playwright 1.64.0。不是对各仓库未来 main 的承诺。

MiniWoB 派生 workload：4 个任务模板 × 3 个 seed × 6 个状态 = 72 个共享状态；六个观察方式 = 432 次捕获。另有 24 个本地商品样例状态、144 次捕获，单独报告。

| MiniWoB 页面上的表示 | 新输出 token 合计 | 调用耗时 p50 |
|---|---:|---:|
| Playwright 原生 aria_snapshot | 6,906 | 2.72 ms |
| agent-browser 原生增量 | 12,320 | 40.94 ms |
| Browser Use DOM 表示 | 19,292 | 6.56 ms |
| agent-browser 全量 | 22,191 | 41.11 ms |
| **DeltaDOM 增量** | **36,475** | **73.74 ms** |
| DeltaDOM 强制全量 | 74,943 | 74.23 ms |

全部 576 次捕获无报错；捕获前后页面 fingerprint 一致；DeltaDOM 192 次全量/增量重建均匹配捕获节点。每个进程块结果和完整表见 [summary.json](../artifacts/benchmarks/observation-v1/summary.json)、[table.md](../artifacts/benchmarks/observation-v1/table.md)，原始逐次记录见 [rows.jsonl](../artifacts/benchmarks/observation-v1/rows.jsonl)。

解释：

- DeltaDOM 增量相对自身全量减少 51.3% 新输出，但仍是 agent-browser 增量的 **2.96 倍**、Browser Use DOM 文本的 **1.89 倍**。自建商品样例中也没有击败 agent-browser 增量：25,176 对 20,037 token。
- 这里的 token 是 `cl100k_base` 编码后的新观察文本，未发送给 LLM，不是历史累计 prompt、缓存后费用或模型计费 token。
- 各工具的信息范围并不等价。Playwright aria 不含完整动作工具封装；它不是 Playwright MCP 的完整结果。Browser Use 按自身规则筛选 DOM；agent-browser 带可执行 refs。没有因为文本更短就宣布谁更好。
- DeltaDOM 比较采用 DOM text，不含 settle/API 等附加信息；完整 observation token 也逐行保存。这个口径没有让 DeltaDOM 背负其他工具没测的元数据。
- 时间口径也不等价：agent-browser 包含 CLI/daemon 往返，其他项为进程内调用；Browser Use 这里只测 DomService 而非完整 Agent step。DeltaDOM 默认含至少 60 ms 的安静等待；其 capture 中位数约 2.88 ms，core_boundary 约 0.22 ms。不能称为 Rust 比其他实现慢十倍，也不能称为模型端到端提速。

## 发现的实际缺口

`email-inbox` 的 `.email-thread` 用 JavaScript 监听 click，并通过 cursor:pointer 表示可点击。DeltaDOM 捕获到了文字，但未把这些元素标成 interactive；`#close-email` 无文本图标没有被捕获。当前 `act()` 会拒绝未观察到的交互节点。

这不是缩短文本就能解决的问题。应先修复事件绑定/可点击元素覆盖和无文本图标，再设计紧凑但可重建的序列化。原型当前每个节点反复发送 JSON 字段名；native agent-browser 已有 `--delta`，不能再把“有增量”本身当成领先证据。本轮固定核心，不覆盖负结果。

## 模型对比应如何做

主因果比较：**同一 Browser Use actor、action scaffold、模型、任务、seed、预算，原版观察 vs 接入 DeltaDOM 的观察**。这个原生集成目前未完成。外部工具横向比较另列：Browser Use、agent-browser、Playwright MCP，之后再加 Stagehand；不同 Agent loop 的结果不直接归因于 DOM 压缩。

完整闭环至少记录：原 evaluator 成功率；每个任务的 input/cached-input/output token；总墙钟时间；实际成本（有 provider usage 时）；动作错误、过期 ID、超时与重试。失败任务保留在分母。先预定成功率非劣界限，再判断成本下降是否有价值。

本轮用户指定的 ChatGPT Desktop 三个模型被应用控制权限挡住，记作 not_run；不得用 Codex 工具里的其他模型代替。WorkBuddy DeepSeek V4.1 Flash 的受限原生工具试跑见 [MODEL-PILOT.md](MODEL-PILOT.md) 和 [运行目录](../artifacts/benchmarks/workbuddy-v1)。它用人工 UI relay、放宽页面计时、无视觉/JavaScript 回退，不能当作官方模型排行。

| WorkBuddy DeepSeek V4.1 Flash，固定 seed 11 | 登录 | 删除指定邮件 |
|---|---|---|
| DeltaDOM observe/act | 通过，3 步 | 失败：点击被拒绝，模型放弃 |
| Browser Use DOM/native events | 通过，3 步 | 通过，2 步 |
| agent-browser 原生增量/click/fill | 通过，3 步 | 通过，2 步 |

六次任务全部保留；成功来自环境的 `done=true, raw_reward=1`，不是模型自述。这里只有两个已知开发样例、每格一次，不能外推正式成功率。模型实际计费 token、缓存、费用均不可见。人工传递造成的墙钟时间不用于速度比较。

## 复现观察层

先按仓库贡献指南生成本机 wheel；本轮环境与仓库依赖分离：

```sh
uv venv --python 3.12 .bench/venv
uv pip install --python .bench/venv/bin/python -r benchmarks/requirements.lock
uv pip install --python .bench/venv/bin/python --only-binary=:all: dist/deltadom-0.2.0-cp312-abi3-macosx_11_0_arm64.whl
mkdir -p .bench/node
cp benchmarks/package*.json .bench/node/
npm ci --prefix .bench/node
git clone https://github.com/Farama-Foundation/miniwob-plusplus.git .bench/miniwob
git -C .bench/miniwob checkout 33c3b4ddef8c6eb67c57a29663d844b1eda7e614
.bench/venv/bin/python benchmarks/observe.py --output artifacts/benchmarks/new-run
.bench/venv/bin/python benchmarks/summarize.py artifacts/benchmarks/new-run
```

需要系统 Chrome。脚本默认拒绝覆盖已有输出目录。模型 relay 使用 `model_bridge.py` 与 `relay.py`，不调用模型 API；完整控制条件见 [PROTOCOL.md](PROTOCOL.md) 和 [MODEL-PILOT.md](MODEL-PILOT.md)。npm 锁同时记录安装但本轮未测的 Playwright MCP，不能把 aria_snapshot 行冒称 MCP 实测。
