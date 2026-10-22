# 0.4：能证明什么，不能证明什么

0.4 将首版交付收窄到**浏览器观察的增量记录、检查与离线恢复**。不是通用智能体加速器。原 0.3 感知/编码保留；历史负结果见 [RESULTS-v2.md](RESULTS-v2.md)。

## 同源存储比较

450 份观察来自既有 MiniWoB/本地样例记录，每种来源 150 份、24 段。相同原文分别存为：每帧独立 zlib 压缩并校验的 DDT1、增量 DDT1、整段 JSON 数组的 gzip。每段独立起始；每份解码原文完全相同，450/450 通过。**这是回顾性诊断，旧 holdout 已使用，不再称新确认集。**

| 来源 / 页面 | 独立压缩 DDT1 | 增量 DDT1 | 减少 | 整段 gzip |
|---|---:|---:|---:|---:|
| Browser Use / MiniWoB 开发页 | 30,098 B | 15,428 B | 48.7% | 7,472 B |
| Browser Use / 原 holdout 页 | 18,663 B | 8,985 B | 51.9% | 3,388 B |
| Browser Use / 自建商品页 | 18,802 B | 7,690 B | 59.1% | 4,347 B |
| agent-browser 全量 / MiniWoB 开发页 | 28,127 B | 12,979 B | 53.9% | 5,333 B |
| agent-browser 全量 / 原 holdout 页 | 19,913 B | 9,274 B | 53.4% | 3,672 B |
| agent-browser 全量 / 自建商品页 | 25,788 B | 7,941 B | 69.2% | 5,964 B |

整段 gzip 在所有这些组上更小。如果只需要任务结束后备份，优先使用普通 gzip。DeltaDOM 的用途是运行期间增量记录、检测缺失/损坏、恢复中断前缀和检查具体变化，不是替代通用归档工具。

这里的 agent-browser 全量只是 codec 的同源输入，**没有把其原生 `snapshot --delta` 隐去以宣称工具领先**。原生增量在之前的公开页面新输出比较中仍胜过 DeltaDOM 0.3，详见原报告。上表不包含模型、provider 缓存或成功率；减少的是完整录制文件字节，不能折算费用。

[协议](RECORDING-PROTOCOL.md) · [复现脚本](recording_v1.py) · [逐段原始结果](../artifacts/benchmarks/recording-release/results.json)

## 原生接口与上下文诊断

实际 Browser Use 0.13.11 MessageManager 在六步中始终保留 system + 当前 state，旧 state 会替换掉。因而“保留一份全量加所有差分一定比原生上下文省钱”的前提不成立。记录回调完全不修改输入，模型输入降幅为 **0%**。

[状态槽检查](../artifacts/benchmarks/native-context-v1/results.json)验证原生消息类型和替换语义；[真实 Agent.run 接口检查](../artifacts/benchmarks/native-agent-contract/results.json)验证回调记录与响应器实际收到的消息逐字段一致。后者用脚本响应器测试连接，**不是模型成功率测试**，不计入模型基准。

ChatGPT Desktop 的三组模型测试仍为 `not_run`：当前应用控制权限不允许访问，未绕过限制或改用 SpineCodex。WorkBuddy 旧模型试跑保留为小样本故障回归证据，不扩展成一般优势。

## 发布判断

可发布实验版的理由：安装、实际浏览器演示、录制、逐字段比较、离线校验/恢复形成了可运行路径；录制层在已测同源逐帧压缩基线上有明确体积收益。**尚未满足“主流智能体端到端更强”的标准**，不以成熟产品或通用加速器发布。

复现：`python benchmarks/recording_v1.py --output /tmp/new-recording-run`；输出目录须不存在。安装当前 wheel 后可执行，不需要模型。
