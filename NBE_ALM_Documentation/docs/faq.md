# FAQ - Questions to Expect

**Why not let the LLM do the calculations?**
LLM output is non-deterministic and hard to audit. The engine is plain Python and every number can be reproduced; the LLM only extracts text inputs and explains results.

**How do you know the numbers are right?**
`calculation_validation_table` recomputes NII, NIM, cost of funds, Loan/Deposit, LCR and position interest independently and reports PASS/FAIL for each run.

**How is a rate shock applied?**
The `Market_Data` curve is shifted in parallel, read at each position's reference tenor, multiplied by the pass-through percentage, and applied after every repricing event within the horizon.

**What happens to fixed-rate products?**
They are not repricing-eligible, so a rate shock does not change their interest within the horizon.

**What is the interest convention?**
Simple interest, Actual/365: `Balance × Rate × Days / 365`.

**Why are rates stored as decimals?**
One convention across all tables (`0.123` = 12.3 %) prevents ×100 mistakes. Market yields given as `18.5` are normalized automatically.

**What if Ollama is not running?**
The app keeps working. Free text falls back to regex parsing and the explanation panel shows that the model is unavailable.

**Is data sent outside the bank?**
No. Ollama runs locally.

**What happens if saving fails halfway?**
Each insert is its own transaction. Failures are collected and displayed. A single end-to-end transaction is on the roadmap.

**How do you handle concurrency?**
This is a single-analyst prototype: each simulation is read-compute-write with auto-increment IDs from MySQL. Concurrent safety would be addressed together with authentication in the roadmap.

**Is the LCR regulatory-grade?**
No, it is a proxy built from flagged cash flows. See [Limitations](limitations.md).

**Does loan/deposit growth change NII?**
Currently it changes balances and ratios but not interest; this is item 1 on the roadmap.
