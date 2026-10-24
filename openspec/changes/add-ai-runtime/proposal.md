## Why
CareMemory has a budget governor and contracts but no AI runtime. The doctor needs a nightly memory card per patient: numbers computed in plain Python, prose written by an LLM, every sentence cited and checked, delivered only as an approval draft.

## What Changes
- `cm/memory/features.py`: LLM-free feature helpers (missed doses, streak, weekday pattern, refill gap, quiet days, self-report vs refill conflict).
- `cm/tools/`: read-only governed tools (snapshot, list events, features) with banned-term screening.
- `cm/validator/cite_or_cut.py`: cut uncited or number-mismatched sentences; template fallback.
- `cm/agents/narrator.py`, `cm/agents/orchestrator.py`: Deep Agents orchestrator with write_todos, narrator and drafter sub-agents, interrupt on submit_for_review, Postgres/Memory checkpointer, durability sync.
- `cm/jobs/nightly.py`, `cm/jobs/ai_smoke.py`: job entry points. `cm/store/ai_repo.py`: small repo functions.
- `cm/api/routers/query.py`: Ask box uses the WORKER model with read-only tools when a key is present; canned answer on RED or missing key.
- New dependencies already pinned in requirements.txt: `deepagents==0.7.30`, `langchain-deepseek==1.1.1`, `langgraph-checkpoint-postgres==3.2.0`.

## Out of scope
Sub-agents beyond narrator and drafter, intake, identity, the resume HTTP path, eval harness, sending messages. No change to `cm/contracts/`.

## Owning lane
E/N/D (AI runtime), spec section `feature_specs/02_ai_core_memory.md`.
