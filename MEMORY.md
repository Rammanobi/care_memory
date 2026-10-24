# MEMORY.md: standing instructions for building CareMemory

These instructions were given once by the project owner so they never have to repeat them while rushing. They apply for the whole build. Agents must read this file before editing code. `CLAUDE.md` points here.

## Rule 1: log every code change in OpenSpec automatically

**Applies to:** any code change the owner asks for or approves during the build:
- adding a feature
- removing or disabling a feature
- changing existing behaviour
- fixing an error or bug

**The owner will not remind you.** Record the change in OpenSpec yourself, as part of doing the work. Do not ask permission and do not wait to be told. This standing instruction authorizes the proposal, the code change, and the archive in one go.

> OpenSpec's `/opsx:propose` skill says to stop after planning. **That stop does not apply here**, because this file is the owner's explicit instruction to plan, implement and archive together.

### Procedure (run from the repo root, `caremem/`)

1. **Find or create the change.**
   - `npx openspec list --json` to see whether an open change already covers this work.
   - If not: `npx openspec new change <kebab-name>`, named `add-…`, `remove-…`, `change-…` or `fix-…`.
2. **Write the artifacts by hand** in `openspec/changes/<name>/`:
   - `proposal.md`: use the headings `## Why` and `## What Changes` (OpenSpec warns if they are missing), then **out of scope**, owning lane, and the spec section it implements. If it touches `cm/contracts/` (frozen at `contracts-v1`), say so and give the RFC reason.
   - `specs/<capability>/spec.md`: a **delta** with `ADDED`, `MODIFIED` or `REMOVED` requirements and a scenario for each. Do this for feature add, remove and behaviour changes.
   - `design.md`: only for non-trivial changes.
   - `tasks.md`: a checklist of steps of at most 2 hours, naming the exact files and the tests that prove each one.
3. **Do the code change**, and tick the tasks off as you go.
4. **Validate:** `npx openspec validate <name>`, then fix whatever it reports.
5. **Archive when the work is done and its tests pass:** `npx openspec archive <name> -y`.
   - For pure bug fixes, tooling or doc-only changes that do **not** change intended behaviour, use `--skip-specs`.
   - If the work is unfinished or tests fail, **leave the change open** and tell the owner.

### Bug fixes (fast path)
Keep it light. **Learned on the first real run:** `openspec validate` fails ("Change must have at least one delta") unless you add the line `skip_specs: true` to the change's `.openspec.yaml`. Do that for every pure bug fix, tooling or doc-only change, then validate and archive with `--skip-specs`. Open `fix-<short-name>` with a `proposal.md` containing:
- symptom
- root cause
- fix
- how it was verified

Add a `tasks.md`, and a spec delta only if the fix changed what the system is *supposed* to do. Then archive with `--skip-specs`.

### Reporting
End your reply with **one line**: the change name and its state (`archived`, or `left open: <reason>`). Nothing more.

### What not to log
Typos, formatting, comment-only and whitespace edits. Anything that changes behaviour, data, config or contracts is logged.

## Rule 2: how this applies to sub-agents
Every lane agent follows Rule 1 for its own changes, and records them under `openspec/changes/` with its lane named in `proposal.md`. When the coordinator spawns an agent, it pastes "Follow `MEMORY.md` Rule 1" into the agent's brief.

## Rule 3: hygiene
- Never write secrets, tokens or keys into OpenSpec files or this file.
- Do not commit unless the owner asks.
- **GitHub remote:** `origin` is `https://github.com/Rammanobi/care_memory.git` (the owner's repo; `gh` is logged in as `Rammanobi`). **Push only when the owner says "push".** Never push on your own, never force-push, and never push `.env` or any secret. Check `git status` for secrets before every push.
- Project facts and hard constraints for agents live in `openspec/config.yaml`; the design documents are one folder up (`../INTEGRATION_DECISIONS.md` wins, then `../CAREMEMORY_ARCHITECTURE.md`).
