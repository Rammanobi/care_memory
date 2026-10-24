## Why
The backend now answers patient questions from record chunks with [D-xxxxxxxx] refs and a calm "Not in the record yet." abstain. The doctor Ask page showed those refs as raw text.

## What Changes
- Ask renders [D-xxxxxxxx] refs as clickable chips that open the evidence drawer with date, kind (event/daily/weekly) and snippet taken from `tool_calls_used[].result_preview`.
- Abstain answers get a calm style plus the line "The system only answers from cited records".
- Ask box is pre-scoped on the patient page (new Ask tab): the UI prepends `PT-0142: ` to the question; scope pill with Clear. No API or contract change (QueryIn has no patient field).
- Mock mode has two sample answers (cited, abstain).
- Memory growth strip: skipped, the API exposes no such data.

## Out of scope
Backend, contracts (`cm/contracts/` untouched), Memory growth strip.

## Owning lane
H1/H2 web (web/ only). Implements RAG_STRATEGY_v2 doctor-facing citations.
