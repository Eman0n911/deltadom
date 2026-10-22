# DeltaDOM

**See what changed. Recover what the browser agent saw.**

[中文](README.md) · [Download](https://github.com/Eman0n911/deltadom/releases/tag/v0.4.0) · [Recording guide](docs/RECORDING.md) · [Evidence](benchmarks/RECORDING-RESULTS.md)

DeltaDOM records browser observations, compares changes between steps, and restores captured content offline. It works alongside existing browser tools. Version 0.4 is an experimental release, not a general agent accelerator.

## Try it without compiling

Download the **Apple Silicon Mac** ZIP from Releases, unzip it, and double-click **Start DeltaDOM.command**, or run:

```sh
python3 install.py
```

Requires Python 3.12+ (or uv) and Chrome. No Rust, Node, model account or API key. The real-browser demo runs eight local steps and checks reconstruction. First installation downloads dependencies; the demo uses only a local sample page. This is not a signed standalone desktop application.

In the unpacked folder:

```sh
python3 run.py replay deltadom-output/demo.ddt
python3 run.py diff deltadom-output/demo.ddt --before 2 --after 3
python3 run.py replay deltadom-output/demo.ddt --step 3 --output step-3.json
python3 run.py record https://example.com --count 30 --output example.ddt
```

Recordings stay local and may contain private page/form content. Review them before sharing. A fresh browser session is used; your everyday browser profile is not loaded. Existing recordings and exported files are never overwritten.

## Add recording to Browser Use

Keep your existing `agent`, model and action setup:

```python
from deltadom import BrowserUseRecorder

with BrowserUseRecorder("agent.ddt") as recorder:
    await agent.run(on_step_end=recorder.on_step_end)
```

Tested against Browser Use **0.13.11**. The optional callback copies the last input messages, output and action results at step end. It depends on a private MessageManager field: revalidate after upgrades. It does not capture every provider request/retry, and does not modify or reduce model input. Existing step callbacks can explicitly call `recorder.on_step_end(agent)`.

For Playwright semantic deltas, stable node IDs and guarded actions, see the [SDK](docs/SDK.md) and [example](examples/observe.py).

## Measured, with limits

- **450/450 snapshots restored byte for byte**, from three native observation sources.
- Recording identical Browser Use output used **48.7%–59.1% fewer bytes** than independently zlib-compressed snapshots with the same framing/integrity checks, on the existing local corpus.
- **Whole-session gzip was smaller in every group.** Prefer ordinary gzip for offline backups.
- **No demonstrated model cost or task-success improvement.** Native agent-browser deltas remain shorter on the previously tested public pages; Browser Use native DOM capture remains faster.

[Protocol, results and negative findings](benchmarks/RECORDING-RESULTS.md). This is retrospective storage evidence, not a new held-out or autonomous-agent benchmark. DDT1 uses standard zlib with the preceding snapshot as dictionary; the contribution is the checked recording/recovery workflow, not a new compression algorithm.

## What is recovered?

The exact semantic nodes or native text recorded, not a complete browser state or video. DeltaBrowser capture excludes iframe internals, closed shadow roots and canvas pixels. A record is limited to 16 MiB. Missing/damaged records fail validation. `replay --recover` can recover a verified prefix from an interrupted recording, explicitly marked incomplete. Hashes detect damage; they do not authenticate the origin.

Choose [Browser Use](https://github.com/browser-use/browser-use) for autonomous browser tasks, [agent-browser](https://github.com/vercel-labs/agent-browser) for CLI control, and DeltaDOM for checked incremental observation records and field-level inspection. The projects are not affiliated.

[Contributing](CONTRIBUTING.md) · [MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
