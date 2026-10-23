# V5：做完一步，随结果带回一次独立读取

这是私密研究原型。它取消旧版的强制注册、空集合基线与页面往返，保留 Browser Use 作为执行器。一次 `click_and_read` 最多点击一次，然后在同一浏览器会话的临时页面打开已观察到的结果链接。原页面的输入内容、滚动位置和节点文档保留。工具不会自动再次点击。

一个最小 SDK 用法（当前源码，尚未发布到安装包）：

```python
from deltadom import ObservedEntity, Readback

# page 必须由 browser.new_context().new_page() 创建。
# 这些 URL 和名称由当前可见页面取得，不猜测内部 API 或数据库 ID。
receipt = await Readback(page).check(observed_cart_url, [
    ObservedEntity(observed_product_url, observed_product_name)
])
print(receipt)
```

`present` 只说明本次独立加载的页面出现对应 URL 和名称；已有的商品也会满足。它不声称新加了几件、不判断是不是最便宜、不证明全部任务完成。`unconfirmed` 不等于“没有写入”，尤其不能据此盲目重试付款、发送或增量操作。

非成员类型的任务可以用 `Readback(page).read(observed_view_url)`，返回可见文字、链接及表单控件当前值。没有 main 的页面使用明确标注的 body 区域；多个 main 不猜测。密码和隐藏输入不导出。临时页面共享 cookie/localStorage，不复制原 DOM 或 sessionStorage；登录跳转和读超时保持未确认。独立加载是页面证据，不是数据库事务或防缓存证明。

## 对比如何做

固定任务、干预、种子及预算在 [protocol.json](../artifacts/benchmarks/outcome-v5/protocol.json)。三组均修复 Browser Use 完整读取结果被短摘要覆盖的问题；最终配置恢复原生每轮 5 动作（早期单动作诊断单列）：

- `simple-fixed`：Browser Use + 简单重新读取核对指令。
- `macro-simple`：同上，并提供相同的点击加独立读取工具，返回完整页面证据。
- `inline`：同一个工具；指定已观察实体时返回 URL 与名称的精确匹配，没有指定则返回同样完整的证据。

两个合并工具分支的采集路径、观察权限、动作预算与提示相同，只有实体匹配结果的表达不同。一次点击加读取计 **2** 个单位，不能借合并工具绕过 40 单位预算。全量原始读取保存在控制器记录中；模型只能看到本分支被分配的输出。代码级强对照独立使用精确 href 与名称比对，不能把与它持平包装成算法创新。

全 7 网站 × 2 条件的机械预检只检查独立读取、程序化比对一致性及原页面保留，不做任务、不调用评分器，不能算 BreakingWeb 成功率。所有初次失败与修复复验保留。模型结果另行记录，旧版的负结果不覆盖。

## V6：保持原工具，按请求触发读取

源码还提供 `ActionReadback`。它不需要添加一个新的模型动作或预注册契约：

```python
from deltadom import ActionReadback

# 包住现有动作，动作本身最多执行一次。
action_result, receipt = await ActionReadback(page).run(
    page.get_by_role("button", name="保存", exact=True).click
)
print(receipt)
```

它只记录动作执行窗口内的 POST/PUT/PATCH/DELETE 请求是否结束，不读请求/响应正文。观察到这类请求后，在预算允许时读取新页面。没有观察到时返回 `not_triggered`，并不表示“肯定没写入”。`force_read=True` 是程序化强对照：即便没有这些请求，也做相同的独立读取。Browser Use 实验中的对照只在非链接点击时设置该选项。

该触发条件是启发式：GET 写入、窗口之外延迟发出的请求、其他标签页和后台异步任务不保证覆盖；用 POST 做读取或发送统计信息也可能造成额外核对。请求在动作期间发生不等于已证明它由该动作因果触发。请求结束、HTTP 成功、页面提示都不会被程序直接解释为业务成功。

**默认读取操作后的当前页面。** 商品详情页通常不能证明商品已进入购物车；这时仍需使用 V5 的显式结果页读取。当前没有自动生成完整任务核对条件，也不能用一个局部 receipt 替整个任务盖章。V6 的真实模型比较因桌面免费额度受限尚未完成，不能引用 V5 的局部收益替代。

本机已有开发环境的复现入口（输出文件必须是新路径）：

```sh
DELTADOM_CHANNEL=chrome .venv/bin/pytest -q

# 固定 12 个单次写入组件检查；需本地 BreakingWeb 服务在 18765。
# 这不是模型自主完成任务的成绩。
PYTHONPATH="$PWD/python" .bench/venv/bin/python benchmarks/outcome_v6_writes.py \
  --output artifacts/benchmarks/outcome-v6/new-single-write-run.json

# 重新生成原始记录表，不选最好的回合。
.venv/bin/python benchmarks/outcome_v5_report.py
.venv/bin/python benchmarks/outcome_v5_report.py --directory artifacts/benchmarks/outcome-v6
```

模型脚手架仍是 `benchmarks/outcome_agent.py`；`auto-control` / `auto-signal` 分别启用程序化对照和请求触发方案。两者与其他 V5 分支均使用原生每轮 5 动作、总 40 个实际动作单位；独立读取收费一个动作单位，零自动写入重试。每个回合须使用新的输出目录与独立桌面模型会话。协议和未运行单元分别保存在 outcome-v5 / outcome-v6 的 protocol.json 与 summary.json，未完成项不能写成失败或成功。
