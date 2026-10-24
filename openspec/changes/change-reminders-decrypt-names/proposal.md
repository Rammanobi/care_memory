## Why
Reminders greet the patient as "friend" because the stored name is not decrypted at send time.

## What Changes
In `cm/jobs/reminders.py` decrypt the patient display name via the approved store path and use it in the template, falling back to "friend" only when absent.

## Out of scope
Template wording, other channels.

## Owning lane
Jobs/Channels lane. No change to `cm/contracts/`.
