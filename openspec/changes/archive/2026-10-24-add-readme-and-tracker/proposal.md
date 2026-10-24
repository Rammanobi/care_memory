## Why
Judges read the GitHub repo first. Round 2 (60% of the score) rewards a working demo, technical depth, completeness against the proposed scope and visible feature-level progress. The repo had a short developer README that linked to design docs outside the repo, no progress tracker and no commit plan. Doc-only change: no runtime behaviour changes.

## What Changes
- Rewrite `README.md`: pitch, problem, what is different, screenshots, honest feature status (done / partial / planned), seven Mermaid diagrams, stack, model-to-task table, safety and privacy, repo map, how to run, env variable names, real test counts, rubric mapping, roadmap, team.
- Add `docs/index.html`: the README as one standalone page (inline CSS, Mermaid from jsDelivr with PNG fallbacks, light and dark).
- Add `docs/assets/` (diagram PNGs and sources, about 12 UI screenshots, page preview) and `docs/design/` (copies of the key design docs, including `EVALUATION_PLAN.md` with the 40/60 rubric note).
- Add `TRACKER.md`: build order as feature slices F01..F17, one-commit-per-slice git plan with exact paths, what must never be committed, next steps, one-line progress summary.
- Update `docs/README.md` to index the in-repo copies.

## Out of scope
Any code change; git add, commit or push (the orchestrating session commits); editing `cm/`, `web/`, `tests/`.

## Owning lane
Documentation (coordinator brief). Spec section: none (doc-only, `skip_specs: true`). No change to `cm/contracts/`.
