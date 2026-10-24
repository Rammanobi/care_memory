# Phase index: where each phase's prompts and tasks live

Three layers. Go top to bottom when you want depth.

| Layer | File | What it holds |
|---|---|---|
| 1 Script (the phase prompts) | `PHASES_SCRIPT.md` | Per phase: goal, "explain to owner" script, the APPROVAL PROMPT, execution steps, exit gate, what can go wrong |
| 2 Tasks and steps | `WORK_BREAKDOWN.md` | 109 tasks, each with lane/model, inputs, files, 3-8 steps, deliverable, "done when" check |
| 3 Lane agent prompts | written in Phase 3 (task by H6), stored in `caremem/cm/agents/prompts/` and `handoff/prompts/` | One brief per lane. Not written yet |

Other prompts that already exist: `MOCK_DATA_PROMPT.md` (seed script), `handoff/HANDOFF_TEMPLATE.md` (limit handoff).

| # | Phase | Hours | PHASES_SCRIPT.md line | WORK_BREAKDOWN.md line |
|---|---|---|---|---|
| 0 | Pre-flight | T-14h to H0 | 39 | 67 |
| 1 | Kickoff, go/no-go | H0 to H0:30 | 95 | 340 |
| 2 | Contract freeze | H0:30 to H2:30 | 132 | 445 |
| 3 | Wave 1 build, Integration 1 | H2:30 to H6 | 183 | 624 |
| 4 | Wave 2 build, cut checkpoint H10 | H6 to H10 | 240 | 1015 |
| 5 | Brain on the real store, cut checkpoint H14 | H10 to H14 | 295 | 1438 |
| 6 | Live Ravi loop on GCP | H14 to H18 | 345 | 1700 |
| 7 | Hardening, feature freeze H22 | H18 to H22 | 382 | 1877 |
| 8 | Demo lock | H22 to H30 | 426 | 2047 |
| 9 | Rehearse, final demo | H30 to H36 | 469 | 2253 |

## Summary: what each phase does and which features it delivers
| # | What we do | Features that exist after it |
|---|---|---|
| 0 | Owner setup: keys and spend caps, two Telegram bots, Gmail token, pgvector check, organiser call, `scaffold-v0` commit, roles, commit permission | Nothing user-visible; the project can start safely |
| 1 | Lock the problem statement, go/no-go | Final scope |
| 2 | Freeze data contracts (`contracts-v1`), core DB migration, Ravi Day 3/Day 60 fixtures, 14 lane workspaces | The shared language all lanes obey |
| 3 | All 14 lanes build first versions; tier-2 freeze at H4; prompts by H6; Integration 1; idea-round deck | Event store, simulator, memory engine v1, rules, validator, doctor console shell, district view shell |
| 4 | `decide()`, outbox drainer, Gmail, validator, identity matching, orchestrator; first live Telegram tap; H10 cut checkpoint | Doctor approval gate works; patient tap reaches the system |
| 5 | Memory engine on the real database, nightly job, narrator on real data, Red review path, sweeper, Gmail reply-to-approve, eval on 3 seeds; H14 cut checkpoint | Cited memory cards, risk ranking, approve by email |
| 6 | Full Ravi loop on Google Cloud, console wired live, agent-trace panel, failure drills, first offline recording; twin accounts if usage < 60% | Live end-to-end demo on a public URL |
| 7 | Never-cut checklist, reliability/security/accessibility tests, the 14 top UI items, prototype round, feature freeze at H22 | Polished doctor and patient UI, tested |
| 8 | Precomputed demo seeds, offline recording, Wi-Fi-off drill, demo script, business case, Q&A bank, backup video | Demo that survives bad Wi-Fi |
| 9 | Five timed rehearsals, Q&A drill, no deploys after H32, T-15 checklist, run of show | Final demo |

## How we use it
Present one phase at a time: read its block in PHASES_SCRIPT.md, show the owner the approval prompt, wait for approval, run, report the exit gate. Today the UI (Phase 3's doctor console, H1/H2 lanes, plus the new patient app) is pulled forward on purpose: it is the biggest block of Round 2/3 marks.
