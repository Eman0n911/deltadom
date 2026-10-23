# Outcome 实测原始汇总

由 `python benchmarks/outcome_report.py` 从全部 result.json 生成；失败和旧版本不删除、不拼最优值。

`请求` 仅统计桌面中继请求，包含等待桌面的耗时不能视为模型推理速度。`有效完成` 同时要求模型确认与官方后台评分成功，不能代替对任务语义的审计。

购物干预存在同价并列但评分只认原始 SKU 的歧义；官方不通过不必然等于做错字面任务。见 [语义审计](../artifacts/benchmarks/outcome-v1/semantic-audit.json)。

| 回合 | 分支 | 条件 | 后台成功 | 模型声明 | 有效完成 | 请求 | 动作单位 | 秒 |
|---|---|---|---|---|---|---:|---:|---:|
| [dev-agent-browser-intervention](../artifacts/benchmarks/outcome-v1/dev-agent-browser-intervention/result.json) | agent-browser | intervention | False | None | False | 0 | None | 0.1 |
| [dev-agent-browser-v2-intervention](../artifacts/benchmarks/outcome-v1/dev-agent-browser-v2-intervention/result.json) | agent-browser | intervention | True | True | True | 7 | 7 | 241.4 |
| [dev-candidate-intervention](../artifacts/benchmarks/outcome-v1/dev-candidate-intervention/result.json) | candidate | intervention | True | None | False | 18 | None | 382.5 |
| [dev-candidate-v2-intervention](../artifacts/benchmarks/outcome-v1/dev-candidate-v2-intervention/result.json) | candidate | intervention | True | False | False | 18 | None | 416.6 |
| [dev-link-amazon-clean](../artifacts/benchmarks/outcome-v1/dev-link-amazon-clean/result.json) | link | clean | True | True | True | 8 | 9 | 219.7 |
| [dev-membership-intervention](../artifacts/benchmarks/outcome-v1/dev-membership-intervention/result.json) | membership | intervention | True | True | True | 12 | 14 | 312.2 |
| [dev-native-intervention](../artifacts/benchmarks/outcome-v1/dev-native-intervention/result.json) | native | intervention | False | False | False | 10 | None | 254.0 |
| [dev-simple-intervention](../artifacts/benchmarks/outcome-v1/dev-simple-intervention/result.json) | simple | intervention | True | True | True | 9 | None | 223.8 |
| [e001](../artifacts/benchmarks/outcome-v1/e001/result.json) | native | intervention | False | True | False | 13 | 13 | 1397.1 |
| [e002](../artifacts/benchmarks/outcome-v1/e002/result.json) | simple | intervention | True | True | True | 17 | 16 | 301.4 |
| [e003](../artifacts/benchmarks/outcome-v1/e003/result.json) | link | intervention | True | True | True | 19 | 19 | 838.2 |
| [e004](../artifacts/benchmarks/outcome-v1/e004/result.json) | agent-browser | intervention | True | True | True | 16 | 16 | 240.7 |
| [r001](../artifacts/benchmarks/outcome-v1/r001/result.json) | native | clean | True | True | True | 7 | 7 | 175.2 |
| [r002](../artifacts/benchmarks/outcome-v1/r002/result.json) | simple | clean | True | True | True | 9 | 7 | 377.4 |
| [r003](../artifacts/benchmarks/outcome-v1/r003/result.json) | membership | clean | False | None | False | 7 | 8 | 262.9 |
| [r004](../artifacts/benchmarks/outcome-v1/r004/result.json) | agent-browser | clean | True | True | True | 7 | 7 | 362.7 |

## 固定确认集覆盖

覆盖只表示执行过，不表示协议完全合规；r001/r002 的超时设置与后续不同，参见协议修正。not_run 不计为失败；部分结果不能用来宣称胜出。每个单元格保留全部实际运行 ID。

| 任务 | 条件 | native | simple | membership | agent-browser |
|---|---|---|---|---|---|
| amazon_browse_category | clean | r001 | r002 | r003 | r004 |
| amazon_browse_category | intervention | not_run | not_run | not_run | not_run |
| booking_frontier_account_overhaul | clean | not_run | not_run | not_run | not_run |
| booking_frontier_account_overhaul | intervention | not_run | not_run | not_run | not_run |
| gmail_escalation_chain | clean | not_run | not_run | not_run | not_run |
| gmail_escalation_chain | intervention | not_run | not_run | not_run | not_run |
| lms_complete_mixed_module | clean | not_run | not_run | not_run | not_run |
| lms_complete_mixed_module | intervention | not_run | not_run | not_run | not_run |
| pp_transfer_prescription | clean | not_run | not_run | not_run | not_run |
| pp_transfer_prescription | intervention | not_run | not_run | not_run | not_run |
| reddit_community_builder | clean | not_run | not_run | not_run | not_run |
| reddit_community_builder | intervention | not_run | not_run | not_run | not_run |
| rh_live_multi_stock_limits | clean | not_run | not_run | not_run | not_run |
| rh_live_multi_stock_limits | intervention | not_run | not_run | not_run | not_run |

## 故障

- `dev-agent-browser-intervention`: {"error": "RuntimeError: agent-browser exit 1: ✗ Session name 'dd-outcome-gmail_gmail_star_email_36799a430e' is too long. Socket path would be 113 bytes (max 103).\nUse a shorter session name or set AGENT_BROWSER_SOCKET_DIR to a shorter path.\n ", "agent_errors": []}
- `dev-membership-intervention`: {"error": null, "agent_errors": ["Contract frozen or mutation controls already used"]}
- `e004`: {"error": null, "agent_errors": ["RuntimeError: agent-browser exit 1: ✗ Could not locate element with role=link name=Go to Cart\n ", "RuntimeError: agent-browser exit 1: ✗ Could not locate element with role=link name=Go to Cart\n "]}
- `r002`: {"error": null, "agent_errors": ["LLM call timed out after 90 seconds. Keep your thinking and output short.", "LLM call timed out after 90 seconds. Keep your thinking and output short."]}
- `r003`: {"error": null, "agent_errors": ["Contract frozen or mutation controls already used", "Contract frozen or mutation controls already used", "Invalid model output format. Please follow the correct schema.\nDetails: 1 validation error for AgentOutput\naction.0.click\n  Extra inputs are not permitted [type=extra_forbidden, input_value={'index': 2380}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden"]}
- `r004`: {"error": null, "agent_errors": ["RuntimeError: agent-browser exit 1: ✗ Could not locate element with role=link name=Go to Cart\n "]}
