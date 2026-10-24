## Why
The memory engine (beliefs, risk, trust, conflicts) is only partly built; nightly cards rely on LLM-free feature helpers alone.

## What Changes
Implement the v1 memory engine in `cm/memory/` per feature_specs/02_ai_core_memory.md: belief updates, risk score, trust, conflict records, all computed in plain Python with `as_of` reads.

## Out of scope
LLM prose, rules R1-R6, contracts.

## Owning lane
Data/memory lane; feature_specs/02_ai_core_memory.md. No change to `cm/contracts/`.
