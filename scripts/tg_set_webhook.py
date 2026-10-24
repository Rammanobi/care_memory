"""Thin wrapper: python scripts/tg_set_webhook.py [--delete]  (see cm/jobs/tg_set_webhook.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cm.jobs.tg_set_webhook import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
