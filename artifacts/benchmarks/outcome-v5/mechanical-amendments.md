# Mechanical preflight amendments (before any v5 model trial)

- r1 retained in mechanical.json: 6 pass, 2 Amazon fail because harness compared the launch URL `/` against the observed routed `/home`; 2 Reddit errors because the prototype unnecessarily required a main region; 4 initial views contain no entity links and were marked unsupported. No actor or official task evaluation was run.
- r2 stdout recorded all 14 passing after using observed URL, explicit body fallback, and full-read fallback where there are no entity links. Report serialization then failed because a relative output path was passed to Path.relative_to(absolute root). No persisted per-cell evidence survived; not counted as a completed validation.
- r3 uses the identical 14 task/condition cells, resolves output paths, and appends each cell before final summary. Main/body region is explicit. Full-view fallback does not manufacture an entity-membership proof. No sample changed or retry count tuned.
