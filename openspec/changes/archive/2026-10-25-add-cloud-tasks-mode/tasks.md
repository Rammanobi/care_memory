## Tasks
- [x] cm/core/tasks.py: cloud enqueue, injectable client, lazy import (tests/unit/core/test_tasks_cloud.py)
- [x] cm/store/task_runs_repo.py: claim, heartbeat, finish (tests/integration/test_tasks_cloud_routes.py)
- [x] cm/api/routers/tasks.py: OIDC guard, /tasks/run, /tasks/drain-outbox, handlers (tests/unit/api/test_tasks_auth.py, integration)
- [x] requirements.txt: google-cloud-tasks 2.26.0 verified with pip index versions
- [x] cm/jobs/migrate.py: idempotent and non-zero exit on failure (tests/integration/test_tasks_cloud_routes.py)
