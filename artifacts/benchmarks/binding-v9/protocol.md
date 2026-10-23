# V9 relational action binding (before implementation)

Development observation: native Browser Use 0.13.11 history matching followed by
its real click tool selected Invoice B after two identical Approve buttons were
reordered, despite the recorded action targeting Invoice A. Both button hashes
were identical. This is a replay-matcher finding, not an autonomous-agent score.

Hypothesis: compiling visible relational identity at recording time can preserve
record identity across reordering without model calls or per-site selector code.
Capture the selected control and nearest context that contains visible unique
link identity. Do not guess which of several plausible links is the business key:
retain all distinguishing links in that minimal context. If no such context,
allow only an initially unique named control. No positional/hash fallback.
No business-goal inference, amount validation, safe retry or server correctness claim.

Controls: actual installed native history matcher plus native Tools.click; manual
exact link+control relational Playwright locator (strong oracle-configuration
baseline); automatic binding. Same original demonstration and page changes.
No model and no retries. Target is the record identified by its observed href AND
visible name; a changed identity must not be silently accepted.

Fixed cases, all retained: duplicate unchanged; reorder; record remount; wrapper
change; inserted preceding record; target removed; duplicate target identity;
link name changed; unrelated timer; link URL changed; globally unique control;
new duplicate of a global control; no-link repeated records reordered; invisible
handler identity change. 14 x 3 = 42 cells. Include abstention cost: available
correct target vs refused, incorrect action, correct action, justified refusal.
No-link repeated controls and invisible handler changes are explicit counterexamples.

Decision: a narrow replacement for record-relative replay requires zero wrong
visible-identity actions in the declared supported scope, no rejection of normal
reorder/remount/wrapper/noise cases, and agreement with the hand-coded semantic
baseline there. Report unsupported cases and setup requirements separately. This
cannot establish superiority over Browser Use's autonomous agent or cloud workflows.

Then test portable capture/resolve on ALL original 7-site x 2-condition BreakingWeb
initial views (fixed original manifest, no model or scorer). No filtering sites
by coverage. UI errors and unsupported controls remain in denominator. This is
coverage/integration, not task completion. Native full-agent comparison remains
required before broad replacement claims. Do not replace the original task matrix.
