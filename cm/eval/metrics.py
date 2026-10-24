"""Lane J: pure evaluation metrics (no I/O)."""

from __future__ import annotations

from collections.abc import Sequence


def brier(p: Sequence[float], y: Sequence[int]) -> float:
    """Brier score (mean squared error of probabilities)."""
    if not p:
        return float("nan")
    return sum((a - b) ** 2 for a, b in zip(p, y, strict=True)) / len(p)


def auroc(p: Sequence[float], y: Sequence[int]) -> float | None:
    """Rank AUROC with tie handling; None when only one class is present."""
    pos = [a for a, b in zip(p, y, strict=True) if b]
    neg = [a for a, b in zip(p, y, strict=True) if not b]
    if not pos or not neg:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def calibration_bins(p: Sequence[float], y: Sequence[int], n_bins: int = 10) -> list[dict]:
    """Reliability data: per bin mean predicted, observed frequency, count."""
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for a, b in zip(p, y, strict=True):
        bins[min(n_bins - 1, int(a * n_bins))].append((a, b))
    return [
        {
            "bin": i,
            "lo": i / n_bins,
            "hi": (i + 1) / n_bins,
            "n": len(b),
            "mean_pred": (sum(x for x, _ in b) / len(b)) if b else None,
            "observed": (sum(z for _, z in b) / len(b)) if b else None,
        }
        for i, b in enumerate(bins)
    ]


def ece(bins: list[dict]) -> float:
    """Expected calibration error from calibration_bins output."""
    n = sum(b["n"] for b in bins)
    if not n:
        return float("nan")
    return sum(b["n"] * abs(b["mean_pred"] - b["observed"]) for b in bins if b["n"]) / n
