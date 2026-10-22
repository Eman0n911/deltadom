# Python SDK：把观察接入自己的代码

如果只是体验，请从 [真实浏览器演示](../START_HERE.md) 开始。SDK 需要你已有一个 Playwright Page；它不会调用模型。

```python
import asyncio
from playwright.async_api import async_playwright
from deltadom import DeltaBrowser, StateMirror

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        page = await browser.new_page()
        async with DeltaBrowser(page) as delta:
            await page.goto("https://example.com", wait_until="domcontentloaded")
            observation = await delta.observe()
            print(observation.text)
            mirror = StateMirror()
            complete_nodes = mirror.apply(observation.frame)
            print(f"Read {len(complete_nodes)} semantic nodes")
        await browser.close()

asyncio.run(main())
```

## 执行动作

```python
target = observation.find(tag="input", attr=("name", "query"))[0]
await delta.act(observation, target["id"], "fill", "Rust")
observation = await delta.observe()
```

支持 click、fill、select、check、uncheck。一次动作消耗一次 observation；过期状态、替换节点、捕获字段或捕获子树已变化的目标会拒绝执行，需要重新 observe。业务任务结束条件由调用者验证。

## 保存上下文

每次 delta 都依赖 base_seq。保留最近 full + 连续 delta，或通过 StateMirror 重建。丢帧、切换接收者或模型上下文裁剪时，调用 `await delta.observe(force_full=True)`。只把一个 delta 发给没有历史的模型，会缺少信息。

## 允许接口数据

```python
DeltaBrowser(page, api_fields={"https://your-app.example/api/items": ["name", "price"]})
```

默认不采集接口。仅投影配置端点中的指定标量字段，不重放请求；API 数据和 DOM 分开。缺失 Content-Length、压缩或大于 1 MiB 的响应会跳过并报告。该限制是当前 Playwright body 读取方式的保守边界。

主文档与 open shadow DOM 可用；iframe 内部、closed shadow、canvas 像素及完整 AX 名称算法不支持。语义捕获本身有筛选；“重建一致”指筛选后的节点，不指完整网页无损。完整说明见 [DESIGN.md](DESIGN.md)。

## 0.3 文本协议

结构化 `Observation.frame` 保持 version 1；`frame["text"]` 使用文本 version 2，不再兼容手工解析旧文本行的代码。推荐让模型会话先接收一次 `TEXT_GUIDE`，之后按顺序接收观察。

```python
from deltadom import TEXT_GUIDE, TextMirror

receiver = TextMirror()
print(TEXT_GUIDE)  # 将协议说明放入模型的固定工具说明
nodes = receiver.apply(observation.frame["text"])
assert nodes == list(observation.nodes)
```

全量用嵌套树表示父子与兄弟位置，保留每个节点 ID、文字、属性、role 和 interactive。完全相同的重复结构在更短时使用表格。差分 `patch` 仅含变化字段；attrs 合并，`null` 表示删除一个属性键。`add` 的列由全量中的 `columns` 给出；`remove` 删除 ID。`TextMirror` 只读取发送文本，丢帧或跨 document 会拒绝应用，需请求全量。

点击覆盖包括原有 HTML/ARIA 控件，以及 `onclick`/函数属性或 `cursor:pointer` 提示的元素；无文字 CSS 图标可保留类名供解释。它不是完整事件监听器枚举：没有语义、点击属性或鼠标指针提示的 `addEventListener` 目标仍可能漏掉，继承的 pointer 样式也可能带来额外候选。完整可访问名称、iframe、closed shadow、canvas 仍不支持。

默认每次观察仍保留至少 60 ms 的稳定窗口。已有外部稳定控制时，可显式设置 `quiet_ms=0`，但那是调用者改变等待策略，不是默认性能收益。
