"""Container entrypoint: `python -m cm [command]`. One image, role chosen by argv or env.

Commands (argv wins over env): api | worker | migrate | drain-outbox | sweeper | nightly [--patient X]
| reminders | seed | eval. Extra args are passed to the job (e.g. `python -m cm nightly --patient P1`).

CM_ROLE=api|worker  serve FastAPI (and the built web app) on $PORT; SIGTERM drains in-flight requests.
CM_ROLE=job         run `python -m cm.jobs.$CM_JOB` (nightly|sweeper|seed|eval|migrate).
"""

from __future__ import annotations

import os
import runpy
import sys


JOB_COMMANDS: dict[str, str] = {
    "migrate": "migrate",
    "drain-outbox": "outbox_drainer",
    "nightly": "nightly",
    "reminders": "reminders",
    "seed": "seed",
    "eval": "eval_job",
}


def run_command(cmd: str, args: list[str]) -> int:
    """Run one named job in-process; returns an exit code. Unknown command -> 2."""
    if cmd == "sweeper":  # stub until the sweeper duties land (cm/jobs/sweeper.py is lane E)
        print("cm-sweeper: not implemented yet, nothing to do (exit 0)", flush=True)
        return 0
    module = JOB_COMMANDS.get(cmd)
    if module is None:
        print(f"unknown command {cmd!r}; known: api, worker, sweeper, {', '.join(sorted(JOB_COMMANDS))}", file=sys.stderr)
        return 2
    argv = list(args)
    if cmd == "drain-outbox" and "--once" not in argv:
        argv.append("--once")  # a job must exit; the loop mode is for local dev
    old = sys.argv
    sys.argv = [f"cm.jobs.{module}", *argv]
    try:
        runpy.run_module(f"cm.jobs.{module}", run_name="__main__", alter_sys=True)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        sys.argv = old
    return 0


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] not in {"api", "worker"}:
        sys.exit(run_command(args[0], args[1:]))
    role = args[0] if args else os.environ.get("CM_ROLE", "api")
    role = role.strip().lower()
    if role == "job":
        job = os.environ.get("CM_JOB", "").strip()
        if not job.isidentifier():
            sys.exit("CM_JOB must name a module in cm.jobs")
        runpy.run_module(f"cm.jobs.{job}", run_name="__main__", alter_sys=True)
        return
    if role not in {"api", "worker"}:
        sys.exit(f"unknown CM_ROLE {role!r}")
    import uvicorn

    from cm.core import lifecycle

    config = uvicorn.Config(
        "cm.api.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),  # noqa: S104 (container)
        port=int(os.environ.get("PORT", "8080")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        timeout_graceful_shutdown=int(os.environ.get("CM_SHUTDOWN_GRACE_S", "25")),
        log_config=None,
    )
    server = uvicorn.Server(config)
    base_exit = server.handle_exit

    def handle_exit(
        sig: int, frame: object
    ) -> None:  # SIGTERM/SIGINT: flag long handlers, then drain
        lifecycle.request_shutdown()
        base_exit(sig, frame)  # type: ignore[arg-type]

    server.handle_exit = handle_exit  # type: ignore[method-assign]
    server.run()


if __name__ == "__main__":
    main()
