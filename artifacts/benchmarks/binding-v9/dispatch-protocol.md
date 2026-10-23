# Trusted input dispatch experiment (frozen before implementation)

Question: can identity checks be kept valid while Playwright waits for actionability
and sends pointer events? A separately awaited read/check can become stale before
a real click. Test whether validating the bound visible identity synchronously in
capture-phase pointer/mouse/click events prevents this gap without replacing real
input with JavaScript .click(). This is a component experiment, not a task score.

All arms get the same demonstration and single attempt, no retries or model calls:
1. Hand-configured exact record link + named button Playwright Locator.click.
2. The same locator, immediate identity read before Locator.click.
3. Hand-configured same-turn JS resolve + element.click (strong atomic simple
   baseline, retains its lack of trusted pointer events).
4. V9 ActionBinding resolution + ElementHandle.click (current candidate).
5. V9 binding + synchronous capture-phase guard around trusted pointer events.

Fixed cases (each fresh page): unchanged; remount; ordinary reorder; duplicate
identity; target removed; hover recycles the target row to another identity;
pointerdown recycles it before click; ancestor capture click handler recycles it;
preexisting window capture click handler recycles it; pointerdown handler mutates
identity AND writes immediately (known irreducible side-effect boundary); hidden
handler changes effect with identical DOM (known information limit). Run all 11
under both ordinary and isTrusted-required click handlers (22 x 5 = 110 cells).
The isTrusted variant is an explicit synthetic capability stressor, not a claim
that all real websites require it. Inspectable page JS creates the transitions;
the component may use rendered identity only, never the fixture's action log.

Correct means exactly one intended-record effect when the original target remains
available. If it changes after pointer movement, safe refusal is appropriate.
Refusals on unchanged/remount/reorder are failures. Race outcomes count incorrect
effects, not merely API exceptions. Record actual isTrusted and event phase.
A window guard cannot undo earlier app listeners or pre-click side effects and
must preserve failures in those cases. Never describe this as remote exactly-once.

Acceptance for the dispatch mechanism: reproduce at least one wrong ordinary
trusted click under a visible identity change; prevent it without false refusal
on supported unchanged/remount/reorder; report comparison with the atomic simple
baseline and all limitations. This alone does not qualify for broad Browser Use
replacement; combine with portable capture, native replay, and usable integration.

Additional native comparator (registered before execution): installed Browser Use
0.13.11 Tools.act(click index), using the original native snapshot, on all 22
existing cases. This is the direct action path, not rerun_history matching.
One tool call; preserve the tool's own input behavior and internal fallbacks.
No model. The candidate's existing fixed results remain unchanged. This separates
actual native input behavior from the Playwright relational-locator control.
