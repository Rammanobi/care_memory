## Why
Simulated clock day offset looks off by one in sim runs. Documented only; not yet investigated or fixed.

## What Changes
Symptom: sim day numbering/clock offset disagrees with expected day index. Root cause: unknown. Plan: reproduce with a unit test on `cm.core.clock`, fix the offset, verify against sim output.

## Out of scope
Anything beyond clock offset.

## Owning lane
Sim/Core lane. No change to `cm/contracts/`.
