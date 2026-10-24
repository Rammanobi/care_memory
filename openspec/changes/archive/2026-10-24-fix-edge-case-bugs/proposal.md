## Why
Adversarial edge-case tests (`tests/integration/test_edge_cases_api.py`) found real bugs before the public push.

## What Changes
Pure bug fixes, no intended behaviour change. Owning lanes: G (core API), B (suppress), F (router banned list, Telegram inbound).

| Symptom | Root cause | Fix |
|---|---|---|
| Patient writes a request containing a banned word ("TB") and gets HTTP 500 | `portal_new_request` looked the new row up in the banned-filtered list (`StopIteration`) | `_created()` returns a plain receipt text for withheld text; doctor still reads the original (`cm/api/routers/portal.py`) |
| `GET /requests?code=abc`, `/notes`, `/evidence`, `/messages` gave 500 | `code.split("-", 1)[1]` on a code with no dash | use `token_from_code` (`cm/api/readmodels.py`) |
| NUL byte in any text field gave 500 | psycopg `DataError` unhandled | handler returns 422 `invalid_value` (`cm/api/main.py`) |
| Huge `cursor` on `/review/queue`, `/patients`, `/admin/audit` gave 500 (bigint overflow) | unbounded `int(cursor)` | `parse_cursor` clamps, ASCII digits only (`cm/api/deps.py`) |
| Reminder request accepted `99:99 pm`, `13:00 pm`, `0:00 am`, Arabic digits | regex `\d{1,2}:\d{2}` | real 12-hour pattern, ASCII only (`cm/api/portal_models.py`) |
| Doctor gate and portal let `T.B.`, `ethionamide`, `MDR`, Telugu/Hindi disease words through; only the sender blocked them | two different banned-word lists | `cm/api/suppress.find_banned` also applies `cm/router/banned`; added `టీబీ`, `mdr`, `xdr`, `rhze` there |
| `/Stop` or `/STOP` did not stop messages | case-sensitive `startswith("/stop")` | lower-case the command (`cm/channels/tg_inbound.py`) |
| Ask box "who is quiet" answer had `numbers_verified=false` | "3 or more days" not in the cited rows | threshold added to the tool-call args (`cm/api/routers/query.py`) |

Out of scope / left open: doctors are not scoped to their own clinic (district-wide console by design today; xfail test records it); supporter `ask` with a banned word stores the request then returns 422.
Touches no frozen contract.

## Verification
New file `tests/integration/test_edge_cases_api.py` (all pass) plus the full `pytest -m 'not live and not slow and not docs'` run.
