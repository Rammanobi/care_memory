"""Adapter: a LangChain chat model that routes every call through cm.core.llm.GovernedModel
(PII guard, budget check, retry, usage recording), so deep agents can use it as their model."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool


class GovernedChat(BaseChatModel):
    gov: Any
    task_id: str = "adhoc"
    task_type: str = "nightly_patient"
    patient_id: str | None = None

    @property
    def _llm_type(self) -> str:
        return "governed"

    def bind_tools(self, tools: Any, **kw: Any) -> Any:
        return self.bind(tools=[convert_to_openai_tool(t) for t in tools], **kw)

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kw: Any) -> ChatResult:
        if stop:
            kw["stop"] = stop
        msg = self.gov.invoke(messages, task_id=self.task_id, task_type=self.task_type,
                              patient_id=self.patient_id, **kw)
        return ChatResult(generations=[ChatGeneration(message=msg)])
