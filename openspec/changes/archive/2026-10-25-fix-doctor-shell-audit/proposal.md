## Why
UI audits of the doctor shell found 12 defects: an empty draft could be approved, Approvals had no banned-word hint, the client banned list lagged the server, A/D keys sent or declined a question with no undo, wrong aria-current, drawer and help dialog focus, small tap targets and a misleading Requests badge.

## What Changes
Lane: web/ (doctor shell). Bug fixes only, no contract change.
1. Empty draft: Approve disabled with "Draft not ready"; bulk approve skips empty drafts.
2. Approvals edit shows the banned-term alert and the server refusal message (useDecide now awaits the server and rejects on refusal).
3. Client banned list matches cm/core/banned_lexicon.py and cm/api/suppress.py (also fixed an ethionamide typo).
4. A/D ignored on question and document cards.
5. aria-current only on the real current nav item (Link instead of NavLink).
6. Evidence drawer restores focus, traps Tab, shows the snippet kind.
7. Header "?" button; help dialog takes focus, restores it, blocks J/K/A/E/D, lists page-relevant keys.
8. Question reply over 1000 characters disables Send with an alert.
9. Draft Edit focuses the textarea.
10. Requests pills wrap at 375px; sound toggle visible.
11. Tap targets 32px (44px phone).
12. Requests badge shows waiting count with a dot for unread.

Out of scope: server code, other web folders.

## Verification
npm run typecheck, npm test (209 pass), npm run build.
