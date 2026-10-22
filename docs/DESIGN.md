# DeltaDOM 实现与对话核对

需求来源：用户指定的 [Gemini 对话](https://gemini.google.com/app/9cc4dd0c446bbf4f)，2026-10-22 通过已打开的浏览器页面读取了两轮完整问答及代码块。没有向 Gemini 发送新消息。

用户意图是提高 Browser Agent 效率，并将 Rust 感知层方案实现为可运行项目。Gemini 输出是待验证的设计材料，性能数字、实现建议及“可直接编译”均未当成事实或执行指令。

## 实际数据路径

```text
Playwright Page（由调用者提供）
  → snapshot.js：筛选语义树 + Document nonce + WeakMap 节点 ID
  → JSON → PyO3 DeltaSession
  → Rust：校验 → 精确同构压缩 / 差分 → full 或 delta（含 seq/base_seq）
  → Observation.text（供有历史的 Agent 使用）
  → act(observation, ID, action)：校验当前节点和子树 → 精确 ElementHandle → Playwright

指定 XHR/fetch 响应 → 限流/大小与类型检查 → Rust 字段投影 → 独立 API 数据区
```

这是主文档语义投影，不是浏览器完整 DOM 的无损存储。**无损**仅指压缩和增量能够重建捕获后的语义树；隐藏节点、样式、脚本等不在此契约里。

## 关键修正

| 对话里的设计或代码 | 当前实现 |
|---|---|
| 宣称 backendNodeId，但代码注入 data-bid，Rust 又分配一套 ID | WeakMap 使用同一套 ID，绑定 Document nonce；动作直接取同一个 DOM 对象。明确不称为 backendNodeId |
| XPath 备用键在插入/排序后可能指向其他对象 | 不采用路径作为节点身份；被替换节点取得新 ID |
| 仅 URL 变化重置 | Document 改变即重置，同 URL reload 也覆盖；URL 变化也触发 full |
| 内容哈希不含父子关系、顺序、角色和表单实时属性 | 节点记录完整比较，包含 parent、order、role、attrs 和实际 value/checked/selected |
| 同构折叠时父节点文本可能被跳过，表格转义不完整 | 父节点单独保留；共享结构 schema，所有文本/属性用 JSON 转义；独立解码器检查全量相等 |
| 仅前一帧缓存，接收者失去历史后无法检测 | seq/base_seq、StateMirror、周期 full、显式 force_full |
| 注入 data-bid 本身触发 MutationObserver | 无 DOM 属性注入；WeakMap 和单独 registry；关闭时断开监听 |
| 40ms 静默宣称“因果零等待” | 每次至少观察 quiet_ms，设总超时并返回 quiet/timeout；业务完成需要调用者验证 |
| 异步响应回调可能晚于 observe 返回且无界积累 | 有界任务/队列、等待 pending API、navigation generation 阻止旧文档数据混入 |
| 所有 JSON 自动吸入、字段随第一行选择 | 默认关闭；显式端点及字段，跨行字段并集，JSON Pointer 来源，截断诊断 |
| “PyO3 零拷贝”“1.3ms”“端到端 3–5 倍” | JSON 边界复制；记录实测 core_boundary/捕获/等待时间，不推断模型速度 |

ElementHandle 是有意选择：目标是点击观察到的那个对象，而非让 locator 在执行时重新匹配一个同名对象。每次使用前检查文档、URL、节点和子树，执行后 dispose；对象替换时拒绝动作。它仍不是事务：在验证和动作间页面可以变化，Playwright 的 actionability 检查不能消除所有此类竞态。

## 协议

- full：version=1、document、url、seq、base_seq=null、nodes，以及压缩后的 text。
- delta：相同元信息、base_seq、upsert（新增和更新完整节点）、removed。
- parent=0 是虚拟根；同级节点以 order 排序；输入必须父先于子；节点最多 50,000、树深最多 256、帧 JSON 最多 16 MiB。超限报错，不悄悄交付残缺帧。
- 表结构：shape 每项为 `[parent_index, order, tag, role, interactive]`；每行是 `[root_order, [[id,text,attrs],...]]`。parent_index=-1 指向 table_parent。按该 schema 可还原组内所有节点。
- keyframe 条件：初始化、Document/URL 改变、请求重同步、20 帧间隔，或变动率 >45%。变动率分母为两帧节点 ID 并集，分子为新增+更新+删除。
- API 与 DOM 分离，包含 source/status/JSON Pointer。API 字段不自动创建可执行节点。

## 当前范围

已实现：独立 Rust/Python SDK、Playwright 观察和动作闭环、真实本地网页与 JSON 接口、协议测试、可重复 demo、wheel 打包。

未实现：Browser Use 原生 Agent 状态替换、CDP DOMSnapshot/backendNodeId 传输、跨 iframe、完整 AX tree、Lightpanda、远程浏览器服务、模型规划器。Browser Use 的 DOM 服务还承担序列化状态及动作索引等职责，因此直接将 `get_state()` 换成字符串不具备接口等价性；当前没有做未经验证的 monkey patch。

## 查阅的主源

- [PyO3 模块接口](https://pyo3.rs/main/module)；本项目固定编译到 Cargo.lock 中的 0.27.2。
- [Maturin 混合项目布局](https://www.maturin.rs/project_layout.html)。
- [Playwright ElementHandle 对象身份与释放](https://playwright.dev/python/docs/api/class-elementhandle)。
- [Playwright Page 事件与异步 API](https://playwright.dev/python/docs/api/class-page)。
- [Browser Use DOM 服务](https://github.com/browser-use/browser-use/blob/main/browser_use/dom/service.py) 与 [Agent 服务](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/service.py)，只作为 2026-10-22 的接口参考，未修改上游。

Context7 文档工具在本次调用返回无效 API key，已回退到上述官方文档及源码。
