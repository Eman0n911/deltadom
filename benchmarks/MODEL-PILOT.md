# Chat UI model pilot

0.2.0 historical run below. The 0.3.0 regression rerun is recorded in [RESULTS-v2.md](RESULTS-v2.md); old failures are retained.

Requested models: ChatGPT Desktop GPT-6.1 Sol, GPT-6.1 Luna, GPT-6 Astra; WorkBuddy DeepSeek V4.1 Flash. ChatGPT Desktop access was refused by the computer-use tool, which identifies it as com.openai.codex. Those runs are blocked, not replaced with other models or claimed completed.

WorkBuddy: model selected by UI label. No model API usage/billing totals exposed, so model token usage and cost remain unavailable. Use a fresh conversation per tool arm; two tasks within each arm in fixed order. No prompt or policy tuning. One attempt each, eight native actions maximum.

Frozen small development subset: login-user seed 11 and email-inbox seed 11, MiniWoB revision recorded in PROTOCOL.md. These were selected to exercise a standard form and the observed event-listener coverage gap; they are NOT a held-out confirmatory set. Compare DeltaDOM observe/act, Browser Use DomService/native element events, and agent-browser snapshot --delta/click/fill. Text-only, no screenshot or JavaScript/evaluate fallback. This is a constrained smoke test, not the full native agent capabilities.

Manual relay: send generated prompt text verbatim to the chosen model; save raw visible reply, parse its single JSON action, execute without correcting it, return next observation verbatim. No oracle-generated actions, coaching, retries, or response repair. The model cannot read the benchmark source or judge state; the controller records native raw_reward/done separately. Each arm starts a fresh browser page and fresh observation state. Longer 15-minute task timeout accommodates UI relay; binary evaluator is unchanged. No official MiniWoB score or model speed ranking. Wall time includes operator/UI transport.

Artifacts: exact generated prompts, raw UI replies, executed JSON, tool errors, native verdicts, and final screenshots. Report all attempted episodes, give-ups and timeouts. ChatGPT rows stay not_run unless that exact application/model is actually used.

## Observed results · 2026-10-22

WorkBuddy AI 5.8.4 displayed `Deepseek-V4.1-Flash` for all three conversations. The UI label is the model provenance available here; the backend model identity and sampling parameters are not independently exposed.

| Native observation/action arm | login-user / seed 11 | email-inbox / seed 11 |
|---|---|---|
| DeltaDOM 0.2.0 | passed, 3 actions | failed: rejected noninteractive node, then gave up |
| Browser Use 0.13.11 | passed, 3 actions | passed, 2 actions |
| agent-browser 0.39.1 / snapshot --delta | passed, 3 actions | passed, 2 actions |

All five passed episodes have native `done=true, raw_reward=1`. DeltaDOM email stopped at `done=false, raw_reward=0`, with one attempted click plus a give-up response. Its click on node 16 raised `StaleObservationError: node is not an observed interactive target`. Browser Use first clicked 7 without completing the task, then 6 succeeded; agent-browser opened the email with e1, then clicked e11 successfully. No model actions were corrected or retried by the controller.

These six episodes are a development smoke test with one sample per cell, selected after observing a coverage gap. They do not estimate general success rates or establish model/tool rankings. Conversations retain the earlier login task when moving to email within an arm. All arms were text-only and restricted to click/fill/give_up, not the complete agents' action sets. Wall times include manual transport, a desktop session recovery, and operator delays; do not compare those as model or tool latency. Provider token usage, cache usage and cost are unavailable.

Raw [results](../artifacts/benchmarks/workbuddy-v1/results.json), [action trace](../artifacts/benchmarks/workbuddy-v1/actions.jsonl), prompts, copied replies and final screenshots are retained. A UI transport timeout before the Browser Use email second prompt was recovered after checking it had not been sent; the prompt was sent once, without rerunning the model episode. An unrelated visible WorkBuddy reply encountered after a chat switch was discarded and never submitted to the benchmark controller.

| Requested ChatGPT Desktop model | Status |
|---|---|
| GPT-6.1 Sol | not_run: application control denied |
| GPT-6.1 Luna | not_run: application control denied |
| GPT-6 Astra | not_run: application control denied |

The `ChatGPT` application lookup was denied by the computer-use tool, which identified the restricted application as `com.openai.codex`. The available model picker was therefore not inspected. No SpineCodex, alternate application, or substitute model was used for these rows.

## Repeating the manual pilot

After installing the isolated dependencies described in [README.md](README.md):

```sh
.bench/venv/bin/python benchmarks/model_bridge.py --output artifacts/benchmarks/new-model-run
```

Read the current prompt at `http://127.0.0.1:8879`. Paste it verbatim into the selected model's chat. Copy the reply into `benchmarks/relay.py` on stdin; the script saves the raw reply before parsing it. Send the returned next prompt verbatim. Start a fresh model conversation whenever the controller returns `new_chat: true`. Stop when it returns `done: true`; then interrupt the local bridge. Use a new output directory for every run. Never send evaluator state or private benchmark answers to the model.
