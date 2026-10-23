"""All attempts, active-mechanism counts, and explicit not-run cells. No best-of."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/benchmarks/outcome-v5"


def main(directory=OUT):
    directory = directory.resolve()
    protocol = json.loads((directory / "protocol.json").read_text())
    rows = []
    for path in sorted(directory.glob("*/source-binding.json")):
        trial = path.parent
        if trial.name == "channel-stop-preflight":
            continue
        result = trial / "result.json"
        availability = trial / "availability.json"
        if availability.exists():
            block = json.loads(availability.read_text())
            rows.append({"id": trial.name, "status": block["status"],
                         "requests": len(list((trial / "mailbox").glob("request-*.json"))),
                         "responses": block["responses_received"],
                         "availability": str(availability.relative_to(ROOT))})
            continue
        if not result.exists():
            rows.append({"id": trial.name, "status": "incomplete",
                         "requests": len(list((trial / "mailbox").glob("request-*.json")))})
            continue
        data = json.loads(result.read_text())
        actions = [e["action"] for e in data["events"] if "action" in e]
        macros = [a["click_and_read"] for a in actions if "click_and_read" in a]
        rows.append({"id": trial.name, "status": "completed", "arm": data["arm"],
                     "task": data["task"], "condition": data["condition"], "phase": data["phase"],
                     "official_success": data["evaluation"]["success"],
                     "claimed_success": data["claimed_success"], "requests": data["model_requests"],
                     "primitive_units": data["action_units"], "macro_calls": len(macros),
                     "max_actions_per_step": data.get("max_actions_per_step", 1),
                     "entity_projection_calls": sum(bool(m["entity_indices"]) for m in macros)
                        if data["arm"] == "inline" else 0,
                     "read_calls": sum("readback" in e for e in data["events"]),
                     "automatic_read_calls": sum(e.get("automatic_readback", {}).get("read_performed", False)
                                                 for e in data["events"]),
                     "automatic_write_retries": 0, "error": data["error"],
                     "source_binding": json.loads(path.read_text()),
                     "mailbox_request_file_bytes": sum(f.stat().st_size for f in (trial / "mailbox").glob("request-*.json")),
                     "scope": "mailbox requests/file bytes are not provider tokens, cost, or internal desktop generations"})
    matrix = []
    for task in protocol.get("tasks") or protocol["confirmation"]:
        for condition in protocol["conditions"]:
            for arm in protocol["arms"]:
                ids = [r["id"] for r in rows if r.get("task") == task["task_id"]
                       and r.get("condition") == condition and r.get("arm") == arm
                       and r.get("max_actions_per_step") == 5]
                matrix.append({"task": task["task_id"], "condition": condition, "arm": arm,
                               "trials": ids, "status": "recorded" if ids else "not_run"})
    report = {"trials": rows, "planned_model_cells": matrix,
              "no_aggregate_rate": "development revisions and exploratory/confirmation cases must not be pooled",
              "mechanical_only": "mechanical-r3 has 14 UI-read checks, not task completion",
              "ambiguity": "Amazon intervention includes tied-lowest SKUs; retain official score without equating it with literal task semantics"}
    (directory / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    stage = directory.name.removeprefix("outcome-").upper()
    prefix = f"../artifacts/benchmarks/{directory.name}"
    lines = [f"# {stage} 全部运行记录", "", "不合并开发版本、不挑每个样本的最好结果。请求数不等于 provider token 或费用。", "",
             "|运行|分支|任务 / 条件|官方成功|声明|请求|动作单位|每轮动作上限|合并读取|实体投影实际启用|",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["status"] != "completed":
            lines.append(f"|{r['id']}|{r['status']}|—|—|—|{r['requests']}|—|—|—|—|")
        else:
            lines.append(f"|[{r['id']}]({prefix}/{r['id']}/result.json)|{r['arm']}|{r['task']} / {r['condition']}|{r['official_success']}|{r['claimed_success']}|{r['requests']}|{r['primitive_units']}|{r['max_actions_per_step']}|{r['macro_calls']}|{r['entity_projection_calls']}|")
    lines += ["", f"原冻结清单有 {len(matrix)} 个模型比较单元；在原生 5 动作上限下已记录 {sum(c['status']=='recorded' for c in matrix)} 个。", "",
              f"完整未运行清单及源码绑定见 [summary.json]({prefix}/summary.json)。实体投影为 0 时，该回合不能支持身份匹配算法有效性的归因。"]
    (ROOT / f"benchmarks/OUTCOME-{stage}-RAW.md").write_text("\n".join(lines) + "\n")
    for r in rows:
        print(r["id"], r.get("official_success"), r.get("requests"), r.get("primitive_units"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=OUT)
    main(parser.parse_args().directory)
