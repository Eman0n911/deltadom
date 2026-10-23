"""Reproduce read-result loss using the installed native message manager.

This checks context construction, not model task success.
"""

import base64
import hashlib
import json
import tempfile
from importlib.metadata import distribution
from pathlib import Path

from browser_use.agent.message_manager.service import MessageManager
from browser_use.agent.views import ActionResult, AgentStepInfo
from browser_use.filesystem.file_system import FileSystem
from browser_use.llm.messages import SystemMessage
from deltadom.browser_use_delivery import deliver_read_evidence

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "artifacts/benchmarks/outcome-v1"


def main():
    history = json.loads((DATA / "r001/history.json").read_text())["history"]
    raw = next(r for step in history for r in step["result"]
               if "Searched page" in (r.get("long_term_memory") or ""))
    result = ActionResult.model_validate(raw)
    native = json.loads((DATA / "r001/mailbox/request-004.json").read_text())
    actual_prompt = "\n".join(m["content"] for m in native["messages"])
    observations = {}
    with tempfile.TemporaryDirectory() as tmp:
        for label, item in [("stock", result), ("delivery_patch", deliver_read_evidence(result))]:
            manager = MessageManager(task="context construction audit", system_message=SystemMessage(content="audit"),
                                     file_system=FileSystem(base_dir=tmp))
            manager._update_agent_history_description(result=[item], step_info=AgentStepInfo(step_number=0, max_steps=40))
            read = manager.state.read_state_description
            observations[label] = {"read_chars": len(read), "complete_payload_in_read_state": result.extracted_content in read,
                                   "short_memory_retained": any(result.long_term_memory in (h.action_results or "") for h in manager.state.agent_history_items)}
    assert not observations["stock"]["complete_payload_in_read_state"]
    assert observations["delivery_patch"]["complete_payload_in_read_state"]
    assert observations["delivery_patch"]["short_memory_retained"]
    assert result.include_extracted_content_only_once is False  # original is unchanged
    dist = distribution("browser-use")
    identity = {}
    for name in ["browser_use/tools/service.py", "browser_use/agent/message_manager/service.py"]:
        entry = next(p for p in dist.files if str(p) == name)
        digest = hashlib.sha256(dist.locate_file(entry).read_bytes()).digest()
        identity[name] = {"sha256": digest.hex(), "matches_installed_wheel_record":
                          entry.hash.mode == "sha256" and base64.urlsafe_b64encode(digest).decode().rstrip("=") == entry.hash.value}
    report = {"scope": "native context construction, not model efficacy", "browser_use": dist.version,
              "source_record": "r001/history.json", "next_native_packet": "r001/mailbox/request-004.json",
              "full_tool_payload_present_in_actual_packet": result.extracted_content in actual_prompt,
              "short_memory_present_in_actual_packet": result.long_term_memory in actual_prompt,
              "reproduction": observations, "installed_source_identity": identity,
              "limitations": "Does not repair DOM price formatting, native 60k context cap, semantic correctness or lost replies. Patch must also be applied to strong baselines before positive attribution."}
    (DATA / "read-result-delivery-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
