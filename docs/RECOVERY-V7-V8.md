# 断线后不盲目重做：实验性恢复组件

这项功能针对“提交可能已生效，但工具没有拿到结果”。它保护的是重复执行，
不替用户判断任务已经完成，也不提供服务端事务。仍是本地研究版本，不默认开启。

## 两个不同层次

`RecoveryLedger` 在本地 SQLite 中持久记录用户意图，按**业务对象**隔离未决写入。
模型换动作 ID 也无法绕过同一对象的限制。取消、超时、重启不会清除记录。
读取证据带版本：旧读取不能覆盖较新的读取或后续操作。

`NetworkFence` 把限制进一步放到浏览器请求转发处。一次按钮点击也可能触发网页
脚本重复提交，单纯限制工具调用次数对此无效。它将方法、完整 URL、正文原始字节
的摘要与意图绑定，先落盘，再转发；同一精确请求再次出现时中止请求，不伪造成功响应。
转发失败也不返还许可，因为服务器可能已经收到请求。

这是已有持久化、互斥和防重放技术的浏览器适配；不是宣称首创算法。

## 最小接入

只对自己创建、没有其他请求路由器的专用浏览器上下文使用。先根据用户目标和已观察
业务对象构造稳定资源键；不要把临时节点编号或模型随机生成的动作 ID 当作资源键。
下面的字段必须替换为应用实际观察值，不是系统自动理解自然语言的能力。

```python
from deltadom import NetworkFence, RecoveryLedger, WriteIntent

context = await browser.new_context(service_workers="block")
page = await context.new_page()
await page.goto(observed_page_url)

ledger = RecoveryLedger("workflow.sqlite")
intent = WriteIntent(
    operation_id="this-workflow/mark-message-17",
    resource="this-account/message-17/star",
    effect={"starred": True},
)

# 只有明确不允许相同请求重复提交的操作才启用请求层防重放。
# 普通浏览器会话和批量增量操作不适用。
fence = await NetworkFence(
    context, ledger, intent, origin=page.url
).install()
await ledger.execute(intent, observed_button.click)

# read_goal 由集成者实现：从独立页面读取正确的结果视图，返回
# (True / False / None, 可序列化证据)。False/None 都不是安全重试证明。
receipt = await ledger.reconcile(intent, read_goal)
print(receipt)

# 重启后继续使用原数据库和原稳定资源键。
# 新 operation_id 对相同未决 resource 仍会被挡住。
# 请求层限制应在专用 context 的整个生命周期内保留，直到关闭它。
await context.close()
```

`ledger.inspect(id)` 和 `ledger.events()` 提供本地审计记录。
`goal_observed=True` 仅表示该次读取看到目标；不能证明是本次操作造成，也不能保证之后不变。
读失败输出未知，迟到的读取输出 `stale`，不返回可用的目标判断。

## 必须理解的边界

- 数据库与远端网站不在同一事务。若许可已落盘、真正发送前就退出，系统会保守地
  保留未决状态；即便实际上没写入，也不会自动重发。这是明确记录的可用性损失。
- 对象锁不会因为“页面没看到结果”“过了几秒”或正好重试过两次而释放。
  `settle(intent, reason=...)` 是集成者依据应用证据或操作者决定作出的显式结案，
  不是自动推断。错误结案可能允许重复或冲突写入；旧意图 ID 永久不可再次执行。
- 需要所有相关执行者共用同一数据库、稳定对象键和账户/流程命名空间。
  错误对象键、别名 URL、绕开组件的写入、删除数据库都可绕过限制。
- `NetworkFence` 只覆盖当前专用上下文、指定来源、可拦截的 POST/PUT/PATCH/DELETE。
  不覆盖 GET 写入、WebSocket、Service Worker、其他客户端以及服务器内部重复执行。
  `service_workers="block"` 必须在创建上下文时设置；检查当前 worker 列表不能代替它。
- 指纹是精确字节。不同 JSON 排版、令牌、URL 等会得到不同指纹；没有擅自把它们
  当作同一业务操作。HTTP 307 后续请求也存在路由拦截限制，实测反例已保留。
- 同一合法操作本来就要发送两份相同请求时，会被错误拦截。不能默认开启来保护
  所有表单，更不能借由调整重试次数掩盖这个反例。
- 会保存语义资源、效果描述、读取证据和请求摘要；不保存请求正文或响应正文。
  SQLite/WAL 是本地运行数据，不应作为公开示例提交。

## 可重复验证

```sh
DELTADOM_CHANNEL=chrome .venv/bin/pytest -q tests/test_recovery.py
PYTHONPATH="$PWD/python" .venv/bin/python benchmarks/recovery_v7.py \
  --output /tmp/deltadom-recovery-new-run
PYTHONPATH="$PWD/python" .venv/bin/python benchmarks/recovery_v8_network.py \
  --output /tmp/deltadom-network-new-run
```

输出目录必须不存在。V8 脚本自己启动本地 HTTP 服务和 Chrome，无模型、无真实账户。
BreakingWeb 的 16 格组件验证另见 `benchmarks/recovery_v7_browser.py`，需先启动固定版本环境。
完整结果、强基线及负结果见 [研究记录](../benchmarks/RECOVERY-V7-V8-RESULTS.md)。
