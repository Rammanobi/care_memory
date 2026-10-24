"""get_model(role): governed, retried, PII-guarded model access (CLAUDE.md rules 10, 12, 16).

Env names (values only in .env / Secret Manager): ORCHESTRATOR_MODEL, WORKER_MODEL, VISION_MODEL,
EMBEDDING_MODEL, JUDGE_MODEL as "openai:<model>" or "deepseek:<model>"; optional <ROLE>_FALLBACK_MODEL;
CM_DATA_CLASS; OPENAI_API_KEY / DEEPSEEK_API_KEY are read by the provider SDKs at call time only.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from cm.core import budget as _budget
from cm.core.retry import ProviderCallFailed, RateLimiter, call_with_fallback, call_with_retry
from cm.core.tokenize import assert_clean

ROLES = ("ORCHESTRATOR", "WORKER", "VISION", "EMBEDDING", "JUDGE")
OPENAI_ONLY = ("EMBEDDING",)  # VISION may use deepseek:* (image_url data URIs) while CM_DATA_CLASS != real


class ModelConfigError(Exception):
    error_class = "invalid"


_governor: _budget.BudgetGovernor | None = None
_limiter: RateLimiter | None = None


def get_governor() -> _budget.BudgetGovernor:
    """Process-wide governor. Backend swaps in a DB-backed store with set_governor()."""
    global _governor
    if _governor is None:
        _governor = _budget.BudgetGovernor(_budget.BudgetLimits.from_env(), _budget.PriceTable.from_env())
    return _governor


def set_governor(g: _budget.BudgetGovernor | None) -> None:
    global _governor
    _governor = g


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(float(os.environ.get("CM_RPM", "300")), float(os.environ.get("CM_TPM", "200000")))
    return _limiter


def resolve_spec(role: str, *, fallback: bool = False, env: dict[str, str] | None = None) -> str | None:
    """Return "provider:model" for a role from env; enforce provider rules."""
    e = os.environ if env is None else env
    if role not in ROLES:
        raise ModelConfigError(f"unknown role {role}")
    spec = e.get(f"{role}_FALLBACK_MODEL" if fallback else f"{role}_MODEL")
    if not spec:
        if fallback:
            return None
        raise ModelConfigError(f"{role}_MODEL is not set")
    provider, _, name = spec.partition(":")
    if provider not in {"openai", "deepseek"} or not name:
        raise ModelConfigError(f"{role}: provider must be openai or deepseek")
    if provider == "deepseek" and e.get("CM_DATA_CLASS", "synthetic").lower() == "real":
        raise ModelConfigError("deepseek is refused when CM_DATA_CLASS=real")
    if provider == "deepseek" and role in OPENAI_ONLY:
        raise ModelConfigError(f"{role} requires openai")
    return spec


def _build_default(spec: str, role: str) -> Any:
    if role == "EMBEDDING":
        from langchain.embeddings import init_embeddings  # lazy: tests need no keys

        return init_embeddings(spec)
    from langchain.chat_models import init_chat_model  # lazy

    return init_chat_model(spec)


def _text_of(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    if isinstance(messages, (list, tuple)):
        return "\n".join(_text_of(m) for m in messages)
    if isinstance(messages, dict):
        if messages.get("type") in {"image_url", "image"}:
            return ""  # image bytes are not text; the real-data image guard is _has_image
        if "text" in messages:
            return str(messages["text"])
        return _text_of(messages.get("content", ""))
    if isinstance(messages, tuple):
        return str(messages[-1])
    return _text_of(getattr(messages, "content", str(messages)))


def _has_image(messages: Any) -> bool:
    if isinstance(messages, dict):
        return messages.get("type") in {"image_url", "image"} or _has_image(messages.get("content"))
    if isinstance(messages, (list, tuple)):
        return any(_has_image(m) for m in messages)
    c = getattr(messages, "content", None)
    return isinstance(c, list) and _has_image(c)


class GovernedModel:
    """Wraps a LangChain model: PII guard, budget check, rate limit, retry, fallback, usage recording."""

    def __init__(self, role: str, *, governor: _budget.BudgetGovernor | None = None,
                 limiter: RateLimiter | None = None, builder: Callable[[str, str], Any] = _build_default,
                 env: dict[str, str] | None = None) -> None:
        self.role, self._env, self._builder = role, env, builder
        self._gov, self._lim = governor, limiter
        self._cache: dict[str, Any] = {}

    @property
    def gov(self) -> _budget.BudgetGovernor:
        return self._gov or get_governor()

    def _inner(self, spec: str) -> Any:
        if spec not in self._cache:
            self._cache[spec] = self._builder(spec, self.role)
        return self._cache[spec]

    def _spec(self) -> str:
        pol = self.gov.policy()
        if pol.template_only and self.role != "EMBEDDING":
            raise _budget.TemplateOnlyMode("RED: LLM drafting disabled, use templates")
        role = self.role
        if pol.model_tier == "worker" and role in {"ORCHESTRATOR", "JUDGE"}:
            role = "WORKER"
        return resolve_spec(role, env=self._env) or ""

    def invoke(self, messages: Any, *, task_id: str = "adhoc", task_type: str = "other",
               patient_id: str | None = None, **kw: Any) -> Any:
        text = _text_of(messages)
        assert_clean(text)  # prompt must already be tokenized (text parts only)
        env = os.environ if self._env is None else self._env
        if _has_image(messages) and env.get("CM_DATA_CLASS", "synthetic").lower() == "real":
            raise ModelConfigError("images are refused when CM_DATA_CLASS=real (no real patient images to an LLM)")
        spec = self._spec()
        gov, pol = self.gov, self.gov.policy()
        est_in = _budget.estimate_tokens(text)
        est_out = pol.max_draft_tokens or est_in
        name = spec.partition(":")[2]
        gov.check(name, est_in, est_out, task_id=task_id, patient_id=patient_id)
        (self._lim or get_limiter()).acquire(est_in + est_out)

        fb_spec = None if self.role == "EMBEDDING" else resolve_spec(self.role, fallback=True, env=self._env)
        fb_name = fb_spec.partition(":")[2] if fb_spec else ""
        used = {"name": name}

        def run(s: str, n: str) -> Callable[[], Any]:
            def _go() -> Any:
                used["name"] = n
                m = self._inner(s)
                return m.embed_documents(messages if isinstance(messages, list) else [text]) \
                    if self.role == "EMBEDDING" else m.invoke(messages, **kw)
            return _go

        try:
            out = call_with_fallback(
                run(spec, name), run(fb_spec, fb_name) if fb_spec else None,
                allow_fallback=lambda: gov.can_afford(fb_name, est_in, est_out, task_id=task_id,
                                                      patient_id=patient_id))
        except ProviderCallFailed as e:
            if e.error_class == "spend_cap":
                gov.mark_billing_error()
            raise
        usage = getattr(out, "usage_metadata", None) or {}
        gov.record(model=used["name"], tokens_in=usage.get("input_tokens", est_in),
                   tokens_out=usage.get("output_tokens", est_out if usage else est_out // 2),
                   task_id=task_id, task_type=task_type, patient_id=patient_id)
        return out

    # ---- embeddings (role EMBEDDING only): governed, retried, PII-guarded, usage recorded ----
    def embed_documents(self, texts: list[str], *, task_id: str = "adhoc", task_type: str = "embed",
                        patient_id: str | None = None) -> list[list[float]]:
        if self.role != "EMBEDDING":
            raise ModelConfigError("embed_documents is only available for the EMBEDDING role")
        if not texts:
            return []
        for t in texts:
            assert_clean(t)  # texts must already be tokenized
        spec = self._spec()
        name = spec.partition(":")[2]
        gov = self.gov
        est_in = sum(_budget.estimate_tokens(t) for t in texts)
        gov.check(name, est_in, 0, task_id=task_id, patient_id=patient_id)
        (self._lim or get_limiter()).acquire(est_in)
        try:
            vecs = call_with_retry(lambda: self._inner(spec).embed_documents(list(texts)))
        except ProviderCallFailed as e:
            if e.error_class == "spend_cap":
                gov.mark_billing_error()
            raise
        # the embeddings API returns no usage through LangChain: record the same estimate used to gate
        gov.record(model=name, tokens_in=est_in, tokens_out=0, task_id=task_id, task_type=task_type,
                   patient_id=patient_id)
        return [list(map(float, v)) for v in vecs]

    def embed_query(self, text: str, *, task_id: str = "adhoc", task_type: str = "embed",
                    patient_id: str | None = None) -> list[float]:
        return self.embed_documents([text], task_id=task_id, task_type=task_type, patient_id=patient_id)[0]


def get_model(role: str, **kw: Any) -> GovernedModel:
    """The only way to get a model. Fails fast on bad env; no network, no keys needed here."""
    if role not in ROLES:
        raise ModelConfigError(f"unknown role {role}")
    m = GovernedModel(role, **kw)
    resolve_spec(role, env=m._env)
    return m


get_chat_model = get_model  # name kept from the original stub
