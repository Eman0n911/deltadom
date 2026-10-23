# V7 recovery protocol — fixed before implementation

Question: can browser outcome recovery prevent duplicate effects across process loss,
new planner action IDs, and stale read completions, without rejecting independent work?
This is a component experiment, not a claim of novel distributed-systems theory.

Mechanism: durable semantic resource fences, immutable intent binding, and read evidence
bound to a resource revision. A fresh UI absence does not prove a write was not committed.
No automatic expiry, retry, or conversion of absence into safe-to-retry. A confirmed goal
is evidence at read time; it is not a receipt proving which action caused it.

Input is a caller-supplied semantic resource and effect (same for all controls). Automatic
natural-language/entity discovery is out of scope. Wrong/missing resource keys remain a
failure boundary. Local SQLite ledger must survive process restart; browser/server actions
are not in its transaction. At most one admitted callback, not exactly-once remote execution.

Fixed deterministic matrix (all cases retained): normal; loss before dispatch; loss after
remote commit; commit hidden by delayed UI; same-ID concurrent delivery; new-ID concurrent
replanning; unrelated object; changed payload under same ID; delayed old verification;
read error; negative read after unknown write; caller cancellation. Each case has a single
initial attempt and at most one explicit recovery invocation. No timer/retry-count search.

Controls: (1) fresh exact-goal check then act, (2) durable request-ID journal with a fresh
read, (3) independent SQLite resource-lock baseline with immutable payload/revision checks,
(4) candidate. Control 3 is the strongest simple baseline and may tie the candidate. Do not
remove it, weaken it, or claim innovation from beating only controls 1/2.
Report admitted callbacks, forbidden duplicate admissions, safe independent admissions,
false confirmations, unresolved outcomes, and raw events. Refusing everything cannot win.
No model, no endpoint payload/private truth read by components. Fault driver/ground truth
are evaluator-only. These deliberately constructed cases are developmental, not BreakingWeb.

External check: original BreakingWeb manifest, seed 42 and conditions unchanged. First use
existing Gmail/Amazon development surfaces for browser integration; retain their no-op
interventions as expected unresolved cases, never tune retries to the injector. Original
7-site task matrix remains separate and must not be replaced by this new fault suite.
No model spend until the mechanism passes these cheaper checks. User permits paid runs,
but this phase has zero model spend. Repository remains private; no push/publication.

Browser integration matrix fixed before execution: existing development Gmail star and
Amazon category/cart, clean + intervention, four same controls = 16 cells. Each cell
performs one original UI action then injects a lost caller acknowledgement; recovery
reopens the same ledger and submits one new action ID for the same observed entity.
No arbitrary repeated retries. A shared independent result-view read is used afterwards.
Report calls/admissions and visible goal, not evaluator success or model task completion.
