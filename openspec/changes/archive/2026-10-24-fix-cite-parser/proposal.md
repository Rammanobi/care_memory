## Why
Symptom: in the live PT-0142 run (cm/agents/NOTES.md finding 2) the narrator model wrote citations as
`[E-a, E-b]` (several ids in one bracket). `cite_or_cut` saw no ref and cut correct, grounded sentences as
`no_ref`, wasting model output and pushing cards toward the template fallback.

Root cause: `cm/validator/cite_or_cut.py` matched only the single-ref form `\[([EBCRGD]-id)\]`.

## What Changes
- Fix: `refs_of` now uses a tolerant group pattern: a bracket that starts with a ref-shaped id may hold more
  items separated by `,` or `;` (`[E-a, E-b]`, `[E-a;B-x]`). Every item is returned as written, so a non-id item
  (`[E-a, see note]`) or a fabricated/other-patient id still fails the evidence lookup and the sentence is cut
  (`unknown_ref`). `numbers_of` strips the whole group so ids never count as numbers. `CITE` is kept for callers.
- No intended behaviour change for valid single-ref text; strictness for unknown ids is unchanged.

Out of scope: prompt changes in `cm/agents/narrator.py`; per-sentence (local) number checks.
Lane: D (validator), done inside the J-lane AI eval work (`add-ai-eval-suite`). No `cm/contracts/` change.

## Verification
- Golden cases `cc-comma-in-bracket`, `cc-comma-no-space`, `cc-semicolon-in-bracket`, `cc-te-comma-refs` keep;
  `cc-comma-with-fabricated`, `cc-comma-with-prose` cut as `unknown_ref`; narrator case `nar-comma-refs` keeps
  the sentence (fixtures/ai_evals/, tests/evals/test_ai_evals.py).
- Existing tests unchanged and green: tests/unit/ai (narrator, orchestrator), tests/redteam.
