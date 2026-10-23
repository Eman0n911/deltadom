# 结果核对原型（私密实验）

原型已接入 Browser Use 的实际工具循环。使用者给出自然语言任务；模型从页面选择对象身份和结果页链接，程序完成重新读取和逐对象核对。它还不是通用自动办事产品，当前没有证据优于简单重读。

## 可以实际运行什么

- 新的 `LinkMembershipVerifier`：从已观察到的对象链接或当前详情页的标题绑定 URL 与可见名称，允许先浏览、排序和筛选，再检查该对象是否新出现在结果页。不要求跨页面恰好展示两段相同身份文本；同名但 URL 不同不会通过。支持重复的同对象链接，但不把链接数量当成商品数量。
- `PresenceVerifier`：核对某条已知记录是否新出现在结果列表中，例如邮件进入星标列表。源页必须唯一匹配；操作前结果页必须没有该记录；操作后重新读取必须恰好匹配一条。每个对象使用至少两个可见身份字段，防止仅凭同名文本匹配。
- `OutcomeVerifier`：供开发者声明具体字段，重新读取后检查文本、输入值、勾选状态或指定语义属性。实验中让模型直接生成 CSS 和属性出现了错误；它保留为底层组件，不作为默认自然语言接口。
- `benchmarks/outcome_agent.py`：真正调用 Browser Use 0.13.11 或 agent-browser 0.39.1，通过所有者指定的 WorkBuddy 模型独立决策。保存未经修补的请求、回复、浏览器动作与最终评分。

SDK 中最短的成员核对流程：

```python
from urllib.parse import urljoin
from deltadom import PresenceVerifier

# page 是调用方已经打开的 Playwright 页面，下面的内容来自页面观察。
result_link = page.get_by_role("link", name="Starred", exact=True)
readback = urljoin(page.url, await result_link.get_attribute("href"))
check = PresenceVerifier(
    [["Alice Chen", "Project Update — Q1 Milestones"]], readback
)
await check.prepare(page, page.goto)  # 独立读取结果页，再返回源页
await page.get_by_role(
    "button", name="Star Project Update — Q1 Milestones", exact=True
).click()
check.invalidate()  # 每次动作尝试都让旧证据失效
receipt = await check.verify(page, page.goto)
print(receipt)  # new_membership_observed 或 unconfirmed
```

这是接口示例，使用的是 BreakingWeb 邮件开发任务，不是通用邮箱脚本。浏览器智能体集成时必须通过自身导航接口（本实验为 `BrowserSession.navigate_to`）读取页面，使节点引用缓存同步；不能悄悄绕过框架导航后继续用旧引用。

链接版使用 `LinkMembershipVerifier([{"url": observed_url, "label": observed_name}], readback_url)`，同样调用 `prepare / invalidate / verify`。URL 与名称必须来自当前页面，`prepare` 会重新检查来源；结果页必须是正常 UI 提供的读取入口。集成工具 `prepare_link_membership` 直接接收观察到的节点编号，模型不编写 URL、CSS 或价格属性。

原先基于两段文本的 v3 在第一个哈希选中购物任务失败，已否决其作为默认方案：排序被误判成写操作，契约无法注册。链接版针对这个问题改用相关对象的操作前基线，不再用“任何非链接动作发生过”禁止准备。Amazon 任务已经用于诊断，链接版在它上面的验证只算开发回合。旧版失败记录完整保留，不能把它替换为修复版成绩。

## 证据代表什么

`new_membership_observed` 仅表示所选结果页上出现了指定可见对象。结果页选错、任务遗漏了其他要求、页面缓存或延迟更新，都可能使它无法代表任务真实完成。它不读取隐藏后台状态，不证明数据库提交，不保证并发原子性，不自动重放不确定的写操作。官方任务评估与模型输出严格分离。

链接版的 `new_link_membership_observed` 具有同样边界，尤其不能证明“该商品最便宜”。URL 是页面提供的对象标识，不保证服务端映射永远稳定。接收到 `invalidate()` 的并发动作会使正在核对的结果失效；调用方未通知的后台变化仍可能发生。

没有记录容器、身份不唯一、结果页本来已有对象或任务不属于成员关系时，返回未确认或明确错误。复杂表单、跨步骤任务的完整语义覆盖尚未解决；不能靠拒绝这些任务宣称可靠性胜出。

## 本地验证

```sh
DELTADOM_CHANNEL=chrome .venv/bin/pytest -q
python3 benchmarks/outcome_report.py
```

本机使用已安装 Chrome；不指定 channel 会尝试未安装的 Playwright bundled Chromium。BreakingWeb 的构建、冻结样本和桌面模型通道见[试验协议](../benchmarks/OUTCOME-PROTOCOL.md)，每次试验的源码副本与原始模型输出见[完整汇总](../benchmarks/OUTCOME-RAW-RESULTS.md)。

真实模型结果与发布判断见[实测结论](../benchmarks/OUTCOME-RESULTS.md)。原生读取结果的可选适配修复位于 `deltadom.browser_use_delivery.deliver_read_evidence`；它只修复观察内容进入下一轮上下文的路径，未启用于已冻结的模型对比，不代表已经验证了任务成功率提升。
