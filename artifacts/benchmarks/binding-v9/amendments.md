- replay-r1: all 42 cells retained. Automatic binding falsely refused after JSON
  serialization because JS compared object insertion order via JSON.stringify,
  while the SDK serialized sorted keys. Corrected equality to compare named fields
  and fixed ordered link tuples. No case, condition, retry limit or native baseline
  changed. Focused regression covers serialize/reload plus reorder/remount/wrapping.
- Initial development probe on about:blank produced an empty native selector map.
  Moved it to an actual HTTP URL routed by Playwright; this is environment repair,
  not a successful native-match run. The saved probe uses that valid HTTP setup.
- replay-r3 preserved all 100 scheduled cells. Four harness errors in the added
  record_changed_owner_stays case were a JS selector quoting error, corrected
  without changing the case. Found a genuine candidate bug: after deleting the
  target control, ancestor search widened to the list and bound another record.
  Corrected resolution to recompile the nearest current identity context and
  require the original witness set AND scope tag. No ancestor widening fallback.
  New identity metadata may now cause false refusal; this conservative limitation
  is retained. Added regression for missing control with record link still present.
- First text fallback test attempt omitted DELTADOM_CHANNEL=chrome and failed all
  nine browser setups (missing Playwright bundled Chromium). Chrome rerun executed;
  one assertion incorrectly assumed a newline in inline innerText; corrected the
  assertion to inspect the identity span. No implementation behavior changed for it.
- replay-r4 preserved 100 cells, including 17 harness errors (empty native button
  map) during concurrent coverage/replay jobs. BrowserSession focus auto-recovery
  after closing each context can race the next cell's assigned focus. Changed
  replay harness to a fresh BrowserSession connection for each cell, disconnecting
  it before closing that cell's context. No sample or retry change. coverage-r2
  itself completed 14/14, 597/1016 captured, 597 same-node, zero wrong bindings.
- Preserve the specific ambiguous_identity diagnostic when a formerly globally
  unique named control becomes duplicated; previous refactor returned generic
  identity_not_found. This affects reason reporting, not whether a click is allowed.
- dispatch-r1 completed all 110 cells. Window-only validation prevented hover and
  pointerdown recycle before click, but failed when a later document capture
  listener changed identity. Extended the guard along the actual ancestor capture
  path and use synchronous MutationObserver.takeRecords between listeners, with
  cached resolution when nothing changed. No scenario removed. Side effects
  performed inside an earlier listener, and hidden behavior changes remain limits.
- dispatch-r2 completed all 110 cells, but the resolution cache regressed: the
  observer callback drained records between input events/listeners without setting
  a dirty flag. All six incorrect-effect cases returned. Corrected cache
  invalidation to retain a dirty flag from the callback as well as synchronous
  takeRecords. Raw r2 remains; regression tests include pointermove, pointerdown,
  and document capture mutations, not just final click status.
- buttons-context-r1 completed 281 cells: 263 correct, zero wrong, 18 refusals.
  Audit found 16 avoidable refusals were harness role mismatches: native BUTTON
  elements actually had role=tab, while the simple baseline queried role=button.
  This is NOT a candidate advantage. Correct both simple baselines to use the
  demonstrated element's explicit role (default button). Re-run all 281 targets
  for full-row, generic-context, and candidate; no target removed or timeout
  increased. Preserve original runs and do not report their role gap as benefit.
  Also retain the generic baseline's complete captured fingerprint for diagnosis.
