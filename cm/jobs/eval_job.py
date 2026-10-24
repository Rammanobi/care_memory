"""Lane J: eval job entry point (``make eval``): python -m cm.jobs.eval_job --seeds 2042,2077,2026."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from cm.eval.harness import run_eval

OUT_DIR = Path("out") / "eval"


def run_eval_job(seed: int, out_dir: str | Path = OUT_DIR) -> Any:
    """Eval job entry point."""
    if seed < 2000 and seed != 42:
        raise ValueError("evaluation seeds must be >= 2000 (or demo seed 42)")
    return run_eval(seed, out_dir=out_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="2042,2077,2026")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args(argv)
    for s in (int(x) for x in args.seeds.split(",")):
        r = run_eval_job(s)
        d3, d60 = r["eval_days"]["3"]["model"]["brier"], r["eval_days"]["60"]["model"]["brier"]
        print(f"seed {s}: brier day3={d3:.4f} day60={d60:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
