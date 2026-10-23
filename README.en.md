# DeltaDOM

[中文](README.md) · [English](README.en.md) · [日本語](README.ja.md) · [Français](README.fr.md)

![Concept illustration: a cursor stays tethered to its intended ticket as surrounding records move](docs/assets/brand/identity-thread.png)

**Keep hold of the intended record.** Save its visible identity and recheck it during real clicks.

[Animation](#everyday-scenario-dont-close-the-wrong-ticket) · [Local preview](docs/BINDING-PREVIEW.md) · [Results and limits](benchmarks/BINDING-V9-RESULTS.md)

> **Private development — 2026-10-23.** Public distribution of 0.4 has stopped. The download links below require repository access. End-to-end competitive advantage remains unproven; see the [research decisions](docs/DIRECTION.md), including negative results and criteria for further work. The repository will not become public again without fresh explicit authorization from its owner.

The latest local preview, **0.5.0.dev9**, asks whether a click can still reach the intended record after a list changes. Select a target with Option/Alt-click, save it, and check its identity again during real input. Installation without compilation and the browser demo have been verified in a fresh directory. Fixed scenarios and all buttons across seven test sites show some component-level differences; they do not establish a general replacement for Browser Use. [Preview guide](docs/BINDING-PREVIEW.md) · [API and limits](docs/ACTION-BINDING.md). Source and visuals are in the private repository; the prebuilt preview has **not** been uploaded to GitHub Releases. The older 0.4 downloads do not include these features.

An earlier prototype explores avoiding duplicate submissions after a disconnect, using object-level isolation of unresolved writes and request replay fencing. Browser fault tests show a limited recovery benefit, with missed duplicates and incorrectly blocked legitimate repeats retained. This is not yet a general protection layer and is not included in the 0.4 package. [Usage](docs/RECOVERY-V7-V8.md) · [Fixed comparisons and counterexamples](benchmarks/RECOVERY-V7-V8-RESULTS.md).

**See what changed, step by step.**

[Older preview download](https://github.com/Eman0n911/deltadom/releases/tag/v0.4.0) · [Installation](START_HERE.md) · [Measurements](benchmarks/RECORDING-RESULTS.md) · [Python SDK](docs/SDK.md)

DeltaDOM also records what the browser sees, compares changes between steps, and restores earlier observations offline. Use it to inspect automation, investigate wrong clicks, or preserve changes on dynamic pages.

**0.4 is experimental.** Installation without compilation has been verified on Apple Silicon Macs. Its demo needs no API key, model account, or programming experience. Many linked guides and some CLI messages are currently in Chinese.

## New prototype: see the clicks first

### Everyday scenario: don't close the wrong ticket

A queue keeps refreshing. You select a ticket; if its position changes, follow the same record. If its identity changes during input, pause the click and leave it for review.

![Concept animation: follow the blue ticket through a reorder; pause when it becomes a different orange ticket](docs/assets/brand/identity-motion.gif)

*The illustration and animation explain the mechanism. They are not execution recordings or guarantees of effectiveness.*
[Static version](docs/assets/brand/identity-motion-still.png) · [Real-browser demonstration and limits](docs/TICKET-QUEUE-STORY.md)

### Open the local preview

Unzip the locally supplied **DeltaDOM-0.5.0.dev9-macosx_11_0_arm64.zip** and double-click **Start DeltaDOM.command**. It installs prebuilt binaries and opens a real-browser demo, with no model account required. This ZIP is not on GitHub Releases; the older download below does not contain the new prototype.

In the new preview folder, save a click target of your own. Replace `https://example.com` with the page you want to use:

```sh
python3 run.py bind https://example.com --output action.json
python3 run.py bound-click action.json
```

In the first step, hold Option/Alt and click to select. The second step sends one real click matched to the saved record identity, then leaves the browser open for inspection. Detected identity changes stop the action. There are no automatic retries, and a click is not treated as business success. [Detailed instructions](docs/BINDING-PREVIEW.md).

On ordinary reordering, V9 tied the strong simple context-checking baseline across 281 buttons. In 11 fixed input scenarios, tested separately with ordinary handlers and handlers requiring trusted input, native Browser Use clicks and manual pre-click checks each produced wrong effects in 6 scenarios per handler type; V9 reduced that count to 2. This is not an end-to-end task success rate. [Protocol, strong baselines, all counterexamples and results](benchmarks/BINDING-V9-RESULTS.md).

## Older version 0.4: observation recording

1. [Download and unzip the Mac preview](https://github.com/Eman0n911/deltadom/releases/download/v0.4.0/DeltaDOM-0.4.0-macosx_11_0_arm64.zip). Requires Python 3.12+ (or uv) and Google Chrome.
2. Double-click **Start DeltaDOM.command**, or run `python3 install.py` in the extracted folder.
3. Watch a real browser fill a form, reorder items, select a product and refresh. The terminal should report **Verified 8/8**.

No Rust, Node.js, or compiler is needed. The first installation downloads dependencies; the demo visits only its bundled local page. See the [installation guide](START_HERE.md) for help. This is not a standalone desktop application and is not signed or notarized.

```text
STEP                   FRAME   NODES  FULL BYTES  SENT BYTES  CHECK
initial                full      304      32,556       7,203  OK
unchanged              delta     304      32,556          76  OK
fill                   delta     304      32,560         117  OK
reorder                delta     304      32,576         638  OK
same_url_reload        full      304      32,556       7,203  OK
```

This is an actual demo excerpt from the 0.3 capture core. Version 0.4 retains that encoding and adds verifiable recording files. [Full historical output](artifacts/preview-demo-0.3.txt). These are byte counts from a local example, not model costs.

## Inspect what changed

After the demo, run these commands in the extracted folder:

```sh
# Check recording integrity without starting a browser
python3 run.py replay deltadom-output/demo.ddt

# Compare observations before and after filling the form
python3 run.py diff deltadom-output/demo.ddt --before 2 --after 3

# Restore step 3 as readable JSON
python3 run.py replay deltadom-output/demo.ddt --step 3 --output step-3.json
```

To record a page of your own:

```sh
python3 run.py record https://example.com --count 30 --output example.ddt
```

Interact with the separate browser window; DeltaDOM records once per second. Recordings stay local and may contain private page or form content, so review them before sharing. It does not load your everyday browser's signed-in profile. Existing recording and export files are not overwritten. [Recording, interrupted recovery and integration](docs/RECORDING.md).

## Add recording to an existing agent

In a Python environment with the wheel installed, keep your existing Browser Use model and action logic:

```python
from deltadom import BrowserUseRecorder

with BrowserUseRecorder("agent.ddt") as recorder:
    await agent.run(on_step_end=recorder.on_step_end)
```

The callback has been verified with Browser Use **0.13.11**. It records the last model input, output and action results at each step end. It does not modify model input or capture every provider request and retry. It uses a private MessageManager field, so revalidate after upgrades. [Interface boundaries](docs/RECORDING.md#接入已有-browser-use-智能体).

With Playwright, `DeltaBrowser` also supports semantic-node deltas, stable-ID actions, and explicitly allowed API field reads. [SDK](docs/SDK.md) · [Example](examples/observe.py).

## Measured results

| Comparison | Result | Scope |
|---|---|---|
| Saving identical Browser Use output frame by frame | **48.7%–59.1% fewer bytes** | Compared with independent zlib compression and equivalent integrity checks, on existing page recordings |
| Restoring original content | **450/450 byte-identical** | Three observation sources, 150 snapshots each |
| Whole-session gzip archive | **gzip is smaller** | Prefer gzip if you only need a backup after the task |
| Model cost and end-to-end success | **No improvement demonstrated** | The recording callback does not change model input |

[Protocol, full results and negative findings](benchmarks/RECORDING-RESULTS.md). In earlier observation-layer comparisons on public pages, native agent-browser deltas were shorter and Browser Use native DOM capture was faster. Storage savings do not establish superiority over browser agents.

## Which tool fits?

- For AI that autonomously completes web tasks: [Browser Use](https://github.com/browser-use/browser-use).
- For browser control from the terminal: [agent-browser](https://github.com/vercel-labs/agent-browser).
- For incremental page recording, field-level comparisons, validation and observation recovery: try DeltaDOM alongside your existing tools.

The recording format uses standard zlib with the previous frame as a dictionary. Its value lies in the combination of validation, incremental recording and recovery. It is not a new compression algorithm, and we do not claim other tools lack replay features. The projects are not affiliated.

## Scope and limitations

- V9 saves and replays one click at a time; it does not plan complete tasks. It currently supports common top-level HTML controls and requires the exact saved URL. Some changes escape detection. It cannot undo earlier handler side effects or confirm server-side business results.
- Exact recovery means the captured semantic nodes or native text, not complete HTML, video, or browser state. Playwright capture excludes iframe internals, closed shadow roots and canvas pixels.
- Page observation includes a default 60 ms settling window. It can report instability but cannot guarantee the page will not change later.
- A single recorded step is limited to 16 MiB. Damaged records fail validation. `replay --recover` restores a verified prefix from an interrupted recording and marks it incomplete. Integrity hashes do not authenticate origin.
- The Mac arm64 preview has been installed and verified locally. Source or build checks on other platforms are not installation verification of their downloadable packages.

## Development and contributions

[Historical release checks](docs/VALIDATION-0.4.md) · [Development and tests](CONTRIBUTING.md) · [Design](docs/DESIGN.md) · [Research decisions](docs/DIRECTION.md) · [Changelog](CHANGELOG.md)

MIT · [Third-party notices](THIRD_PARTY_NOTICES.md). Reproducible pages and bug reports are welcome; do not include real passwords, cookies, or personal browsing records.
