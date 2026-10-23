# Workflow Use semantic replay comparator

Upstream browser-use/workflow-use pinned at 5d2d19fe8835cc86f1bf3e04302a5000d590f249.
Its public workflow product already supports semantic recording and no-AI replay;
therefore record-once/no-model alone is not a DeltaDOM novelty claim.

Run all existing 25 replay cases using upstream SemanticExtractor to obtain the
recorded target's semantic key and selectors, then upstream
SemanticWorkflowExecutor.execute_step(ClickStep), which refreshes the current
semantic mapping and performs its normal click verification. No source patch.
Native max_retries=0 means one initial attempt (the executor's loop is
range(max_retries+1)); all other comparator arms also have one attempt. This is
frozen before the arm's results, not tuned retries. No LLM generation or self-heal
is executed, so claims are limited to the deterministic semantic replay path.
Save the whole recorded mapping and actual step used. Unsupported import, mapping,
or browser errors remain errors, not successful refusals. Do not present errors
as evidence of inferior task performance. Existing native history, manual semantic,
full-row, generic-context, and candidate results are all retained.
