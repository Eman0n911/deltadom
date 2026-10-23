# 录制、检查和回放

适合两个问题：网页究竟哪里变了？智能体出错前看到了什么？所有记录只写入你指定的本地文件，不上传。页面文字、表单和模型输入可能包含隐私；先用演示页练习，不要直接公开真实记录。

## 不写代码：录制网页

安装后的终端运行：

```sh
deltadom record https://example.com --count 30 --output example.ddt
```

独立浏览器会打开网页，每秒录制一次，共 30 次。你可以在这个窗口操作。它不会接管日常浏览器，也不会使用你的日常登录态。每次记录捕获的语义节点及稳定性警告；不是视频、网络全量抓包或完整 HTML。

```sh
deltadom replay example.ddt
deltadom diff example.ddt --before 1 --after 10
deltadom replay example.ddt --step 10 --output step-10.json
```

`replay` 离线校验，不打开浏览器、不重做点击。`diff` 显示两步间新增、删除、字段变化。导出恢复指定步的原始记录。已有录制/导出文件不会被覆盖；演示重跑会另存一个带后缀的录制文件。

如果录制因程序退出或断电中断：

```sh
deltadom replay example.ddt --recover --step 10 --output recovered.json
```

只允许恢复中断前完整且校验通过的前缀。报告标记 `complete: false`、`verified: false`，不会将中断录制说成完整成功；损坏数据仍拒绝。哈希用于检测损坏，不提供签名或真实性证明。每次写入会 flush；未执行 fsync，不保证断电时最后一次写入已落盘。

## 接入已有 Browser Use 智能体

已核对版本：**browser-use 0.13.11**。这是可选的记录回调，保留原模型、工具、节点引用与动作流程。它不改变模型输入，也不节省模型 token。

```python
from deltadom import BrowserUseRecorder

# agent 是你已经配置好的 Browser Use Agent，保留原来的模型。
with BrowserUseRecorder("agent.ddt") as recorder:
    await agent.run(on_step_end=recorder.on_step_end)
```

记录每步结束时 MessageManager 保留的最后一份输入消息、模型输出和动作结果。消息内的图片字段也保留。**这不是每次 provider 请求的网络记录**：步内重试、provider 包装、usage 和计费信息不在此接口保证内；失败步骤也可能保留上一份输入，须结合动作错误判断。若已有 `on_step_end`，请在原回调中显式调用 `await recorder.on_step_end(agent)`。

消息数组可能包含历史和 base64 截图，16 MiB 上限针对序列化后的整条 UTF-8 记录，不是单张截图。含 20 张各 800 KiB 截图的消息数组，仅图片经 base64 编码就约 20.83 MiB，可能自然超限；具体保留多少历史取决于 Browser Use 版本与配置。

超限时，`BrowserUseRecorder` 写入 `status: "omitted"`、`reason: "snapshot_too_large"` 的占位记录，包含原智能体步号 `step`、消息数 `message_count`、实际字节数 `raw_bytes` 和上限 `limit_bytes`，不保存该步消息、模型输出或动作结果。回调正常返回，不修改智能体输入，后续步骤继续尝试完整录制。`replay` 报告 `omitted_snapshots`；即使 `verified: true` 和 `complete: true`，也只表示文件完整且校验通过，不代表没有省略的消息。省略内容无法恢复。

本次修复仅处理明确的超限错误。磁盘写入、序列化、接口不兼容等其他错误仍会抛出；若异常退出上下文，文件不带结束封条，已有完整记录可用 `replay --recover` 恢复，不应说成已记录数据全部丢失。

使用了 Browser Use 的 `_message_manager` 内部字段；升级 Browser Use 后应重新执行接口检查。已通过真实 `Agent.run` 的接口测试，测试响应器是固定脚本，不是模型能力或任务成功率试验。历史证据：[native-agent-contract](../artifacts/benchmarks/native-agent-contract/results.json)。

## 任意文本观察也可以记录

```python
from deltadom import TapeWriter, read_tape

with TapeWriter("observations.ddt") as tape:
    tape.add("原生工具返回的第一份文本")
    tape.add("原生工具返回的第二份文本")

# 必须读完，才能验证结束标记。
for entry in read_tape("observations.ddt"):
    print(entry.seq, entry.text)
```

例如 `tape.add(dom_state.llm_representation())` 可保存原生 Browser Use DOM 文本，无需换成 DeltaDOM 的页面捕获。成功写入的文本逐字恢复原文。单步限 16 MiB UTF-8；直接调用 `TapeWriter.add` 超限仍会抛出 `ValueError` 的子类，且不改变文件或录制状态；占位处理只在 Browser Use 回调中进行。流式读取只保留前一步，默认每 20 步保存独立全量检查点。当前读取器顺序读取，不提供随机索引定位。

DDT1 使用标准 zlib、上一份快照的最多 32 KiB 字典、重复帧和全量回退。编码本身不是新压缩算法。它提供的是带长度限制、序号、校验、结束标记和恢复工具的完整工程路径。比较结果同时列出逐帧独立压缩和整段 gzip：[记录实验](../benchmarks/RECORDING-RESULTS.md)。
