"""One tiny live call to each model: `python -m cm.jobs.ai_smoke`.

Prints only role, model name, latency, token counts and OK/FAILED. Never the key or the prompt.
"""

from __future__ import annotations

import time

from cm.core import llm
from cm.core.config import load_dotenv

PROMPT = "Reply with the single word: ready"


def smoke(role: str) -> str:
    spec = llm.resolve_spec(role) or "?"
    t0 = time.monotonic()
    try:
        out = llm.get_model(role).invoke(PROMPT, task_id=f"smoke-{role.lower()}", task_type="eval")
        u = getattr(out, "usage_metadata", None) or {}
        ms = int((time.monotonic() - t0) * 1000)
        return f"{role:12} {spec:32} {ms:6} ms in={u.get('input_tokens', '?')} out={u.get('output_tokens', '?')} OK"
    except Exception as e:  # noqa: BLE001  (print the class only, never the message)
        ms = int((time.monotonic() - t0) * 1000)
        return f"{role:12} {spec:32} {ms:6} ms FAILED ({type(e).__name__})"


def main() -> None:
    load_dotenv()
    for role in ("ORCHESTRATOR", "WORKER"):
        print(smoke(role))


if __name__ == "__main__":
    main()
