# V5 全部运行记录

不合并开发版本、不挑每个样本的最好结果。请求数不等于 provider token 或费用。

|运行|分支|任务 / 条件|官方成功|声明|请求|动作单位|每轮动作上限|合并读取|实体投影实际启用|
|---|---|---|---|---|---|---|---|---|---|
|[a001](../artifacts/benchmarks/outcome-v5/a001/result.json)|simple-fixed|amazon_browse_category / clean|True|True|8|8|1|0|0|
|[a002](../artifacts/benchmarks/outcome-v5/a002/result.json)|macro-simple|amazon_browse_category / clean|True|True|12|13|1|1|0|
|[a003](../artifacts/benchmarks/outcome-v5/a003/result.json)|inline|amazon_browse_category / clean|True|True|13|16|1|4|0|
|[d001](../artifacts/benchmarks/outcome-v5/d001/result.json)|simple-fixed|gmail_star_email / clean|True|True|3|3|1|0|0|
|[d002](../artifacts/benchmarks/outcome-v5/d002/result.json)|macro-simple|gmail_star_email / clean|True|True|3|4|1|1|0|
|[d003](../artifacts/benchmarks/outcome-v5/d003/result.json)|inline|gmail_star_email / clean|True|True|3|4|1|1|0|
|[d004](../artifacts/benchmarks/outcome-v5/d004/result.json)|simple-fixed|gmail_star_email / intervention|True|True|14|14|1|0|0|
|[d005](../artifacts/benchmarks/outcome-v5/d005/result.json)|macro-simple|gmail_star_email / intervention|True|True|8|10|1|3|0|
|[d006](../artifacts/benchmarks/outcome-v5/d006/result.json)|inline|gmail_star_email / intervention|True|True|9|10|1|1|0|
|[d007](../artifacts/benchmarks/outcome-v5/d007/result.json)|simple-fixed|gmail_star_email / clean|True|True|4|4|1|0|0|
|[d008](../artifacts/benchmarks/outcome-v5/d008/result.json)|macro-simple|gmail_star_email / clean|True|True|2|3|1|1|0|
|[d009](../artifacts/benchmarks/outcome-v5/d009/result.json)|inline|gmail_star_email / clean|True|True|2|3|1|1|0|
|[d010](../artifacts/benchmarks/outcome-v5/d010/result.json)|simple-fixed|gmail_star_email / intervention|True|True|14|14|1|0|0|
|[d011](../artifacts/benchmarks/outcome-v5/d011/result.json)|macro-simple|gmail_star_email / intervention|False|False|7|12|1|5|0|
|[d012](../artifacts/benchmarks/outcome-v5/d012/result.json)|inline|gmail_star_email / intervention|True|True|5|9|1|4|0|
|[f001](../artifacts/benchmarks/outcome-v5/f001/result.json)|simple-fixed|amazon_browse_category / clean|True|True|7|7|5|0|0|
|[f002](../artifacts/benchmarks/outcome-v5/f002/result.json)|macro-simple|amazon_browse_category / clean|True|True|5|7|5|2|0|
|f003|partial_channel_block|—|—|—|6|—|—|—|—|

原冻结清单有 42 个模型比较单元；在原生 5 动作上限下已记录 2 个。

完整未运行清单及源码绑定见 [summary.json](../artifacts/benchmarks/outcome-v5/summary.json)。实体投影为 0 时，该回合不能支持身份匹配算法有效性的归因。
