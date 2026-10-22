# Revision v2 evaluation (fixed before live measurements)

Question: does the 0.3.0 candidate repair the observed clickable-element gap and reduce lossless observation text without discarding captured information? Is any gain competitive with native agent-browser delta and Browser Use DOM?

Original 0.2.0 artifacts and scripts are immutable. Development replay uses exactly the recorded original node snapshots, so serialization-only effects have matched information. Two serialization candidates were examined there (flat compact rows, then nested trees). The candidate selected before the live/holdout runs uses nested trees, repeated-schema tables only if shorter in bytes, and field/attribute deltas. No core tuning after holdout measurements.

Live development replay: original four MiniWoB templates, seeds 11/22/33, six states; local-shop separately, eight states. Holdout replay: enter-password, click-tab, click-option; seeds 44/55/66; six states each. Fixed actions are two fills (password/verify), clicks on tab 2/tab 1, checks on radio 0/radio 1. These pages/seeds have not been used for candidate tuning. Setup reads of task HTML determine selectors only. Holdout is small and local, not independent external validation.

All six observation arms and boundaries remain those in PROTOCOL.md. Default DeltaDOM quiet_ms=60 remains enabled. An attempted historical-idle fast path failed the existing timer-churn test and was rejected. Do not compare a no-wait candidate with a waiting baseline. Total budget: 900 captures; no model API calls, retries, dropped failed rows or official leaderboard submissions. Browser/package versions, wheel and source hashes are recorded. Use a new output directory; preserve any failed run.

Each DeltaDOM frame must reconstruct via both StateMirror (structured protocol) and TextMirror (ONLY emitted text). Recount raw bytes and cl100k_base tokens. Preserve full instructions/content/attributes; don't suppress warnings to improve token counts. Compare per family and process, keeping local-shop and holdout distinct. All observation inputs remain synthetic/local.

Mechanism gate: tests must cover clickable custom DOM/listener + empty CSS icon, delayed action mutations, active timer churn, same-URL reload, stale/replaced targets, password redaction, attribute deletion/reparenting, dropped text patches and hundreds of state mutations. Repeat the original native email delete workflow using DeltaDOM's own act() and native MiniWoB reward; distinguish deterministic controller actions from model-selected actions.

Decision criterion: correctness gates all pass; candidate loses no captured facts during serialization; disclose token gains/losses against each competitor separately. A general superiority claim requires later matched-model/action-loop and unseen end-to-end tasks, success non-inferiority and provider cost accounting. A narrow workload advantage may be described only with its exact scope.
