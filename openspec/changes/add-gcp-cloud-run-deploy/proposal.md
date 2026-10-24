## Why
There is no deployment path to Cloud Run.

## What Changes
Add Dockerfiles, Cloud Run services (cm-api, cm-sweeper), Cloud Run Jobs (cm-jobs), Cloud Tasks queues agent-runs, resumes, outbound, and a deploy script/doc.

## Out of scope
Provisioning real secrets in repo.

## Owning lane
Infra lane. No change to `cm/contracts/`.
