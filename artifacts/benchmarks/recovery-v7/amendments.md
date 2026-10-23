# Retained diagnostic corrections

- fault-r1 used a durable request journal without the pre-action fresh-goal read
  specified in the protocol. This weakens that control; do not claim a comparison
  against journal-plus-read from r1. Added the same exact visible-goal read to
  both journal controls. All 12 cases, order, faults and callback bounds unchanged.
  Candidate receives no extra observations. fault-r2 is the corrected matrix.

- After browser-r1 completed, bound loop variables as callback defaults in its
  driver to satisfy Ruff. Each callback had already been awaited before the next
  cell. Runtime source is copied in browser-r1; raw results were not overwritten.
