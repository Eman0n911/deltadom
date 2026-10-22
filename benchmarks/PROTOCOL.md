# Observation-layer pilot · 2026-10-22

Question: on the same frozen browser states, does DeltaDOM reduce newly emitted observation text relative to current mainstream representations, and at what local capture cost? This is a development pilot, not a MiniWoB score or an agent leaderboard.

Frozen before measured runs:

- DeltaDOM: c4df334, installed 0.2.0 wheel; no core changes during this pilot.
- Browser Use: PyPI 0.13.11, native DomService + llm_representation with default attributes and previous state supplied. No screenshot or agent wrapper.
- agent-browser: npm 0.39.1, native `snapshot` and native `snapshot --delta`; no `-i` removal of descriptive content, no arbitrary length/depth truncation.
- Playwright: 1.64.0, native `body.aria_snapshot()`; this is a representation reference, NOT the complete Playwright MCP protocol.
- DeltaDOM: ordinary `observe()` vs `observe(force_full=True)`, default quiet_ms=60, API extraction off. Count both DOM text and full observation separately.
- Native output contracts differ. Content coverage is diagnostic, not information equivalence. The only matched-information contrast is DeltaDOM delta vs DeltaDOM full.

Workloads: upstream MiniWoB++ revision 33c3b4ddef8c6eb67c57a29663d844b1eda7e614: enter-text, login-user, click-checkboxes, email-inbox. Three seeds: 11, 22, 33. Each trace: initial, unchanged, scripted mutation 1, mutation 2, unchanged, same-URL reload. An additional local-shop 8-step trace is reported separately. MiniWoB episode timers are disabled AFTER deterministic initialization to obtain stationary replay states. This modifies native timing and explicitly excludes official success scoring.

Scripts use predetermined Playwright actions to produce shared states; tools do not choose actions. Every adapter reads the same live page; before/after page state fingerprints detect observation-induced mutation. No private data, model, paid API, browser profile, cloud browser, or leaderboard submission. Set Browser Use telemetry/cloud sync off.

Use three independent Chrome process blocks, one per seed. Browser/session creation and import/tokenizer warmup are outside capture timing. Rotate adapter order deterministically; each state is observed once per adapter. Do not retry failed measured rows or drop them. Warmup/preflight errors are retained separately. No performance tuning based on this pilot.

Metrics: raw observation UTF-8 bytes; cl100k_base token count (diagnostic tokenizer, not billed tokens); per-call wall time and native sub-timings where exposed; per-state errors; DeltaDOM exact reconstruction. Preserve raw outputs. Agent-browser timing includes the real CLI invocation and daemon round trip; Python timing is in-process. No claim of pure-core or end-to-end model speedup.

Report per-family and per-process totals, and frame-type breakdown. Do not pool MiniWoB and our fixture into a single promotional percentage. At most 3 process blocks / 96 shared states / 576 capture calls in the main pilot. Stop and diagnose adapter/instrumentation failures before any measured run; preserve aborted runs. Model task success, full prompt/history/cache accounting, native action success and paid cost remain not_run.

Decision: measure the direction rather than assume a win. If DeltaDOM loses to a strong delta baseline or required facts are absent, report it and prioritize the corresponding design gap. Official claims require a later closed-loop experiment with pinned model, common action scaffold/evaluator, task IDs, seeds, budgets, and an a priori success non-inferiority margin.
