"""Ask box with a scripted WORKER model: tool use, grounded answer, and fallbacks (no network)."""

import json
import os

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from cm.agents.fakes import ScriptedChat
from cm.api.main import create_app
from cm.api.routers import query as q
from cm.api.routers.auth import reset_rate_limits

pytestmark = pytest.mark.db
WEB = {"X-CM-Client": "web"}


@pytest.fixture()
def doctor(pinned_clock: None):
    reset_rate_limits()
    c = TestClient(create_app(), headers=WEB)
    pw = json.loads(os.environ["DEMO_USER_PASSWORDS"])["dr.rao"]
    assert c.post("/auth/login", json={"username": "dr.rao", "password": pw}).status_code == 200
    return c


def _call(name, args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "t1"}])


def test_llm_answer_uses_tool_and_is_grounded(doctor, monkeypatch):
    monkeypatch.setattr(q, "llm_available", lambda: True)
    monkeypatch.setattr(q, "_worker_chat", lambda: ScriptedChat(script=[
        _call("get_patient", {"code": "PT-0142"}), AIMessage(content="PT-0142 is flagged, see the record [1].")]))
    r = doctor.post("/query", json={"question": "Why is PT-0142 flagged?"}).json()
    assert r["answer_text"].startswith("PT-0142 is flagged")
    assert r["tool_calls_used"][0]["tool"] == "get_patient" and r["numbers_verified"] is True
    assert set(r) >= {"answer_text", "tool_calls_used", "as_of", "numbers_verified", "latency_ms"}


def test_ungrounded_number_falls_back_to_canned(doctor, monkeypatch):
    monkeypatch.setattr(q, "llm_available", lambda: True)
    monkeypatch.setattr(q, "_worker_chat", lambda: ScriptedChat(script=[
        _call("get_patient", {"code": "PT-0142"}), AIMessage(content="PT-0142 missed 987 doses [1].")]))
    r = doctor.post("/query", json={"question": "Why is PT-0142 flagged?"}).json()
    assert "987" not in r["answer_text"] and r["numbers_verified"] is True


def test_model_error_and_no_key_use_canned(doctor, monkeypatch):
    def boom():
        raise RuntimeError("down")

    monkeypatch.setattr(q, "llm_available", lambda: True)
    monkeypatch.setattr(q, "_worker_chat", boom)
    assert "PT-0142" in doctor.post("/query", json={"question": "Why is PT-0142 flagged?"}).json()["answer_text"]
    monkeypatch.setattr(q, "llm_available", lambda: False)
    assert doctor.post("/query", json={"question": "Who has gone quiet?"}).status_code == 200
