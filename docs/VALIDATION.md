# 本地验证记录

日期：2026-10-22（Asia/Shanghai）。本次交付为本地 MVP；未使用模型、用户登录态或远程业务网站。

## 通过

| 检查 | 结果 |
|---|---|
| `cargo test --locked` | 5 passed |
| `DELTADOM_CHANNEL=chrome .venv/bin/pytest -q` | 10 passed，6.81s |
| `cargo clippy --all-targets -- -D warnings` | 通过，无告警 |
| `.venv/bin/ruff check python tests` | 通过 |
| `maturin develop --release --locked` | 通过，真实 Rust 扩展 |
| `maturin build --release --locked --out dist` | 生成 macOS arm64、Python ≥3.12 abi3 wheel |
| 独立临时 venv 安装该 wheel | 成功；包内 JS/HTML 完整；真实 Chrome 捕获 304 个语义节点 |
| 8 步 demo | 全部完成，每一步 StateMirror 重建结果与该次浏览器捕获逐字段相等 |

测试覆盖：全量压缩文本独立解码、父节点文字不丢失、特殊字符、300 次固定种子的新增/删除/排序/字段修改、重新归属父节点、重复 ID 拒绝、丢帧恢复、周期/显式全量、同 URL reload、过期观察拒绝、节点替换与按钮文字变更拒绝、open shadow DOM 填写、select/checkbox 实时值、密码遮蔽、隐藏节点剪枝、API 默认关闭/字段投影/消费一次、API 行数与大小限制、导航后过期响应隔离、等待超时和监听清理。

其中“导航后过期响应隔离”使用真实页面导航 + 受控延迟 body 对象，以确定性制造竞态；不将这项测试描述成完整真实网络并发测试。其余 API 正向链路使用本地 HTTP 响应。

## 原始演示与测量口径

命令：

```sh
.venv/bin/python -m deltadom.demo --channel chrome --output artifacts/demo.json
```

原始结果：[demo.json](../artifacts/demo.json)，页面图：[demo.png](../artifacts/demo.png)。

环境：macOS 26.6.2 arm64；Python 3.12.13；Playwright 1.64.0；Chrome 156.0.8078.47；Rust cargo 1.97.1。Cargo.lock 和 requirements-dev.lock 固定依赖。

基准是项目自带的 30 条商品列表，8 个预定步骤，不是从公开任务集挑选的结果。比较相同语义内容的三种新输出量，使用实际 `cl100k_base` 编码计数：

| 步骤 | 输出 | 节点 | 全量语义 JSON | 同构压缩全量 | 本次 DOM 输出 |
|---|---|---:|---:|---:|---:|
| 初始 | full | 304 | 9,525 | 3,371 | 3,371 |
| 无变化 | delta | 304 | 9,525 | 3,371 | 59 |
| 输入查询 | delta | 304 | 9,527 | 3,373 | 105 |
| 加载 API | delta | 304 | 9,531 | 3,377 | 98 |
| 列表反转 | delta | 304 | 9,531 | 3,377 | 930 |
| 选择第 7 项 | delta | 304 | 9,530 | 3,376 | 97 |
| 新增商品 | delta | 313 | 9,810 | 3,446 | 346 |
| 同地址刷新 | full | 304 | 9,525 | 3,369 | 3,369 |
| 合计 | | | **76,504** | **27,060** | **8,375** |

- 相对未压缩的完整语义 JSON，DOM 新输出 token 减少 **89.05%**。
- 相对每步发送同构压缩后的全量，增量协议的新输出 token 减少 **69.05%**。
- JSON 字段名比较冗长，故未压缩基线不是强生产基线；第二组比较用于单独显示增量的效果。
- 原始记录字段 `transmitted_dom_tokens` 指本地生成、可供发送的 DOM 文本量。**没有实际发送给模型；不是完整 prompt token、缓存命中率或累计计费 input token。** 保留对话历史会改变后续完整 prompt 的大小，这里没有测量。
- DOM 比较不含 API/等待状态/警告；完整 observation 的编码量另存于 `observation_tokens_including_api`。API 没有 DOM 同等信息基线，因此不纳入上述降幅。
- 文档随机 nonce、临时端口会使重跑 token 数略有差异；时间受机器负载影响。这是一轮功能演示的测量，未作统计显著性或性能归因。

该轮每步 capture 中位数 12.93ms，core_boundary 中位数 0.43ms，observe 总耗时中位数 87.96ms。core_boundary 包含 Python JSON 编解码和 Rust/PyO3 调用，不能称为纯 Rust 计算耗时；observe 包含至少 60ms 的安静观察窗口，不能称为零等待。

## 失败与修复

首次浏览器测试：9 passed、1 failed。失败是 `test_timeout_is_explicit_and_cleanup`：定时更新开始前，等待器用此前的静默时间立即返回 quiet。修复为每次 observe 至少经过配置的 quiet_ms 观察窗口，再判断 DOM/网络静默；修复后 10/10 通过。定时器若晚于窗口才执行，仍需要业务后置条件，此限制保留。

首次静态检查发现一个未使用变量、宽泛异常捕获及导入排序问题，均已修复。Context7 文档查询因 key 无效失败，官方文档直接访问正常。

## not_run / 未实现

- Browser Use 原生 Agent 集成及与其现有 DOM 序列化器的公平比较。
- LLM 任务成功率、全 prompt/计费 token、TTFT、端到端提速。
- WebArena / Online-Mind2Web、真实站点隐藏字段召回率。
- Lightpanda、Linux/Windows wheel、跨 iframe、closed shadow、canvas 视觉回退。

因此不采纳原对话中“3–5 倍提速”“75%+ 真实任务 token 收益”“无 bug”等未验证结论。
