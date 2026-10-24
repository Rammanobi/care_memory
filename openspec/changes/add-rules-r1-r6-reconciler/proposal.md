## Why
Rules R1-R6 (including household contact screening R6, P0) and the reconciler are not complete.

## What Changes
Implement R1-R6 in `cm/rules/` and a reconciler that turns rule hits and memory conflicts into approval drafts only.

## Out of scope
Sending messages, UI.

## Owning lane
Rules lane; INTEGRATION_DECISIONS rulings. No change to `cm/contracts/`.
