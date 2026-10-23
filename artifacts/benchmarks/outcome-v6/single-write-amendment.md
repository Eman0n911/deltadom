# Single-write harness repair

First run retained: all 6 Gmail cells completed; all 6 Amazon cells timed out before the write because the replay selector used the visible button text instead of its observed accessible name. The actual accessible name is `Add <observed product name> to Cart` (confirmed from the sealed native Browser Use trace). Source r1 is retained. R2 changes only that locator and output-path handling, and reruns all 12 cells in the same order. No retry, injector, scorer, task, sample or candidate logic changed.
