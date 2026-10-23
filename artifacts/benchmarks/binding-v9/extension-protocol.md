# V9 extension: fixed before text fallback implementation

The original 14 cases and 14 BreakingWeb views stay in full, unchanged. This
extension is exploratory development, not a held-out benchmark. Original r1/r2
outputs remain immutable.

Mechanism change: if the smallest record context has no distinguishing visible
links, retain all distinguishing visible leaf texts outside controls. This is
an explicit conservative fallback, not an inference of which string is a stable
business ID. Changes to any retained witness can cause refusal. Links remain the
preferred typed witness; text fallback has a different support/abstention tradeoff.

Add fixed cases: linked row price changes; linked row status changes; linked row
identity changes to a name with original as prefix; no-link identity changes;
no-link duplicate identity; no-link price changes; same record name with distinct
links reordered; different records share owner link reordered; record link changes
while owner link stays; target control disappears; target control duplicated in
record. All retained, one attempt, no models/retries.

In addition to native real replay and hand-configured exact semantic locator,
include an independently implemented generic simple baseline: record the nearest
semantic row (article/tr/li/[role=row]) full visible text, then require one row
with that exact text and one matching named control on replay. Global controls
require uniqueness. No component helpers. This is a zero-per-site-configuration
full-row verification baseline, intentionally includes volatile text in its check.
It cannot distinguish identical rows or tolerate changed row metadata, but those
limitations must be demonstrated, not assumed. Manual locator remains the stronger
configuration baseline; no claim that beating full-row check beats manual locator.

Text fallback noise case must remain even if it rejects a valid target. Invisible
handler case remains and is not repaired by guessing hidden state. Report both
incorrect actions and refused valid actions. Any native matcher claim is limited
to the actual tested method/tool, not all Browser Use cloud or autonomous behavior.
