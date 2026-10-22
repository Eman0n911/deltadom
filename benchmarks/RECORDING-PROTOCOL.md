# Recording evaluation, v1

Question: can a live, recoverable recording of **unchanged native output** use fewer bytes than saving each full snapshot with independent compression? This is a storage/transport experiment, not an LLM experiment.

Development probe (not a holdout): previous-state zlib dictionary on the existing 0.3 corpus reduced payload sizes versus independent zlib; whole-session zlib was smaller still. This finding motivated a narrow recording feature. Do not describe this corpus as unseen validation.

Freeze before the complete experiment: DDT1 codec, zlib level 6, dictionary = last 32 KiB of preceding decoded snapshot, full checkpoint every 20 records, exact repeated snapshots emit a repeat record, otherwise choose delta only when its compressed payload is smaller than full. Each record has length, sequence, chain hash and decoded-content hash; a terminal seal detects truncated recordings. Limits: 16 MiB decoded snapshot, bounded decompression. No corpus-specific parameters.

Corpus: all native Browser Use, agent-browser full, and DeltaDOM full text from observation-v2 and holdout-v2, grouped by seed/task; 150 snapshots per source, 450 total. Every group is a separate recording. The previous holdout has now been inspected; this is a retrospective diagnostic, not a fresh holdout.

Comparisons: (A) DDT1 full independently compressed snapshots (checkpoint interval=1); (B) DDT1 adaptive stream (interval=20), identical framing/integrity costs; (C) gzip level 6 of the complete JSON array, a stronger offline archival alternative with different access/recovery properties. Preserve losses to C. Also list raw UTF-8 bytes. Do not compare unequal source content to attribute codec gains. Native agent-browser delta remains covered in RESULTS-v2.md; it is not silently replaced with full in claims about agent-browser token efficiency.

Gate: each decoded snapshot must match the source bytes exactly; every input and codec hash recorded; no omitted episodes, no retries or tuning from results. Report storage per family and tool, not model token/cost/success gains. Decode and encode timings are diagnostic process-local timings only. Resource limit: 450 snapshots, one pass, zero model calls.

Integration check: actual Browser Use 0.13.11 MessageManager and message types; demonstrate replacing the state slot drops old DOM, and recording preserves all message fields/IDs without mutating the originals. This is local contract evidence, not full agent/model success. No provider usage or paid inference.
