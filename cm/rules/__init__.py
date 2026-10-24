"""Lane D: the R1-R6 reconciler (feature_specs/02_ai_core_memory.md F6, INTEGRATION_DECISIONS §a4 M3/M8).

Pure, deterministic functions; no I/O except the injectable loader in ``reconcile.reconcile``;
no LLM. Conflicts cite their evidence as ``E:`` refs; drafts add the ``C:`` ref.
"""

from .drafts import ApprovalDraft, draft_for_conflict, drafts_for_opened
from .fast_path import fast_path
from .reconcile import merge_upsert, open_conflicts, reconcile, reconcile_frame

__all__ = [
    "ApprovalDraft",
    "draft_for_conflict",
    "drafts_for_opened",
    "fast_path",
    "merge_upsert",
    "open_conflicts",
    "reconcile",
    "reconcile_frame",
]
