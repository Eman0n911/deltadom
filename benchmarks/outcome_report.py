"""Summarize every retained trial; never select the best run for a cell."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "artifacts/benchmarks/outcome-v1"
ARMS = ["native", "simple", "membership", "agent-browser"]


def main():
    manifest = json.loads((DATA / "manifest.json").read_text())
    rows = []
    for path in sorted(DATA.glob("*/result.json")):
        result = json.loads(path.read_text())
        evaluation = result.get("evaluation", {})
        requests = result.get("model_requests", result.get("model_calls"))
        errors = [e for e in result.get("agent_errors", []) if e]
        history_path = path.parent / "history.json"
        if result["arm"] == "agent-browser" and history_path.exists():
            errors.extend(r["error"] for r in json.loads(history_path.read_text()) if r.get("error"))
        rows.append({
            "run": path.parent.name,
            "development": result.get("phase", "development" if path.parent.name.startswith("dev-") else "confirmation") != "confirmation",
            "task": result["task"], "condition": result["condition"], "arm": result["arm"],
            "backend_success": evaluation.get("success"), "score": evaluation.get("final_score"),
            "claimed_success": result.get("claimed_success"),
            "official_success_mismatch": result.get("claimed_success") is True and evaluation.get("success") is False,
            "usable_success": result.get("claimed_success") is True and evaluation.get("success") is True,
            "protected_state_failures": sum(not c["passed"] for c in evaluation.get("negative_checks", [])),
            "model_requests": requests, "action_units": result.get("action_units"),
            "wall_seconds": result.get("wall_seconds"), "error": result.get("error"),
            "agent_errors": errors,
        })
    cells = []
    for task in manifest["confirmation"]:
        for condition in manifest["conditions"]:
            for arm in ARMS:
                matches = [r for r in rows if not r["development"] and r["task"] == task["task_id"]
                           and r["condition"] == condition and r["arm"] == arm]
                cells.append({"task": task["task_id"], "condition": condition, "arm": arm,
                              "status": "recorded" if matches else "not_run", "runs": [r["run"] for r in matches]})
    data = {"trials": rows, "confirmation": cells,
            "confirmation_complete": all(c["status"] == "recorded" for c in cells),
            "provider_tokens_cost": None,
            "scope": "Controlled text-only desktop relay, not official paper harness or full BreakingWeb score"}
    if (DATA / "semantic-audit.json").exists():
        data["semantic_audit"] = json.loads((DATA / "semantic-audit.json").read_text())
    (DATA / "summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    lines = ["# Outcome 实测原始汇总", "", "由 `python benchmarks/outcome_report.py` 从全部 result.json 生成；失败和旧版本不删除、不拼最优值。", "",
             "`请求` 仅统计桌面中继请求，包含等待桌面的耗时不能视为模型推理速度。`有效完成` 同时要求模型确认与官方后台评分成功，不能代替对任务语义的审计。", "",
             "购物干预存在同价并列但评分只认原始 SKU 的歧义；官方不通过不必然等于做错字面任务。见 [语义审计](../artifacts/benchmarks/outcome-v1/semantic-audit.json)。", "",
             "| 回合 | 分支 | 条件 | 后台成功 | 模型声明 | 有效完成 | 请求 | 动作单位 | 秒 |",
             "|---|---|---|---|---|---|---:|---:|---:|"]
    for r in rows:
        elapsed = round(r["wall_seconds"], 1) if r["wall_seconds"] is not None else "unknown"
        lines.append(f'| [{r["run"]}](../artifacts/benchmarks/outcome-v1/{r["run"]}/result.json) | {r["arm"]} | {r["condition"]} | {r["backend_success"]} | {r["claimed_success"]} | {r["usable_success"]} | {r["model_requests"]} | {r["action_units"]} | {elapsed} |')
    lines += ["", "## 固定确认集覆盖", "", "覆盖只表示执行过，不表示协议完全合规；r001/r002 的超时设置与后续不同，参见协议修正。not_run 不计为失败；部分结果不能用来宣称胜出。每个单元格保留全部实际运行 ID。", "",
              "| 任务 | 条件 | native | simple | membership | agent-browser |", "|---|---|---|---|---|---|"]
    for task in manifest["confirmation"]:
        for condition in manifest["conditions"]:
            subset = [c for c in cells if c["task"] == task["task_id"] and c["condition"] == condition]
            lines.append("| " + " | ".join([task["task_id"], condition] + [", ".join(c["runs"]) or "not_run" for c in subset]) + " |")
    lines += ["", "## 故障", ""]
    for r in rows:
        if r["error"] or r["agent_errors"]:
            lines.append(f'- `{r["run"]}`: ' + json.dumps({"error": r["error"], "agent_errors": r["agent_errors"]}, ensure_ascii=False))
    (ROOT / "benchmarks/OUTCOME-RAW-RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
