"""Offline tests for cm.rag.render and cm.rag.chunk (no database, no network)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cm.rag import chunk as ch
from cm.rag.render import build_rollup_cards, render_event

TOK = "P-0142"
T0 = datetime(2026, 2, 2, 9, 0, tzinfo=UTC)  # Monday


def ev(type_, payload, day=0, source="telegram", **kw):
    at = T0 + timedelta(days=day)
    return {
        "event_id": uuid4(),
        "type": type_,
        "occurred_at": at,
        "recorded_at": at,
        "source": source,
        "payload": payload,
        "supersedes": None,
        "consent_id": None,
        "channel": "telegram",
        **kw,
    }


def test_render_each_type_no_values_or_names():
    cases = [
        ev("DoseCheckin", {"status": "missed", "for_date": "2026-02-03"}),
        ev(
            "ContextNote",
            {"origin": "patient_text", "kind": "patient_text", "text_tokenised": "I was at work"},
        ),
        ev(
            "Dispense",
            {"tablets": 28, "bill_no": "B-99812", "days_supply": 28, "row_sha1": "abc"},
            source="chemist",
        ),
        ev(
            "LabResult",
            {
                "test": "smear",
                "result": "smear_2plus",
                "rif_resistant": True,
                "report_date": "2026-02-01",
            },
        ),
        ev("SupporterVisit", {"mode": "witnessed", "visit_date": "2026-02-02"}),
        ev(
            "ReviewDecisionEvent",
            {"action": "approve", "kind": "nightly_card", "tier": "amber", "via": "console"},
        ),
        ev("CheckinPrompt", {"for_date": "2026-02-03"}),
    ]
    for e in cases:
        r = render_event(e, TOK)
        assert r is not None and r.text.endswith((".", "work"))
        assert TOK in r.text or e["type"] == "ContextNote"
    texts = " ".join(render_event(e, TOK).text for e in cases)
    for banned in ("28", "B-99812", "smear", "2plus", "abc"):
        assert banned not in texts
    assert render_event(ev("WeightReport", {}), TOK) is None


def test_render_is_deterministic_and_taps_not_embedded():
    e = ev("DoseCheckin", {"status": "taken", "for_date": "2026-02-02"})
    assert render_event(e, TOK) == render_event(e, TOK)
    assert render_event(e, TOK).embed is False
    assert (
        render_event(ev("ContextNote", {"origin": "doctor", "text_tokenised": "x"}), TOK).embed
        is True
    )


LONG = " ".join(f"Sentence number {i} says the patient felt fine today." for i in range(120))


@pytest.mark.parametrize("overlap", [100, 200])
def test_fixed_size_and_overlap(overlap):
    out = ch.chunk_text(LONG, size_tokens=256, overlap_tokens=overlap, strategy="fixed")
    assert len(out) > 2 and all(c.tokens <= 256 + 3 for c in out)
    a, b = out[0].text, out[1].text
    shared = 0
    for k in range(1, len(a)):
        if b.startswith(a[-k:]):
            shared = k
    assert ch.count_tokens(a[-shared:]) >= overlap - 8
    assert out == ch.chunk_text(LONG, size_tokens=256, overlap_tokens=overlap, strategy="fixed")


def test_fixed_rejects_overlap_ge_size():
    with pytest.raises(ValueError):
        ch.chunk_text(LONG, size_tokens=50, overlap_tokens=50, strategy="fixed")
    with pytest.raises(ValueError):
        ch.chunk_text("x", strategy="nope")


def test_sentence_strategy_whole_sentences_and_overlap():
    out = ch.chunk_text(LONG, size_tokens=60, overlap_tokens=20, strategy="sentence")
    assert len(out) > 3
    for c in out:
        assert c.text.endswith(".") and c.tokens <= 60
    last = out[0].text.rsplit(". ", 1)[-1].rstrip(".")
    assert last in out[1].text  # last sentence of chunk 0 is carried into chunk 1


def test_event_and_dynamic():
    assert len(ch.chunk_text(LONG, strategy="event")) == 1
    short = ch.chunk_text("Dose taken.", strategy="dynamic")
    assert [c.text for c in short] == ["Dose taken."]
    long = ch.chunk_text(LONG, size_tokens=100, overlap_tokens=30, strategy="dynamic")
    parents = [c for c in long if c.role == "parent"]
    kids = [c for c in long if c.role == "chunk"]
    assert parents and kids and all(k.parent_seq is not None for k in kids)
    assert all(long[k.parent_seq].role == "parent" for k in kids)
    assert ch.chunk_text("", strategy="fixed") == []


def test_conversation_windows():
    msgs = [f"message {i}" for i in range(10)]
    assert ch.message_windows(msgs) == [(0, 6), (4, 10)]
    out = ch.chunk_messages(msgs)
    assert (
        out[0].text.splitlines()[-1] == "message 5" and out[1].text.splitlines()[0] == "message 4"
    )


def test_telugu_never_split_inside_character():
    te = " ".join(["నేను ఈ రోజు మందు వేసుకున్నాను, కానీ నిన్న మర్చిపోయాను."] * 60)
    for strat in ("fixed", "sentence", "dynamic"):
        for c in ch.chunk_text(te, size_tokens=40, overlap_tokens=10, strategy=strat):
            assert "�" not in c.text and c.text


def test_rollups_from_features_only():
    events = []
    for d in range(14):  # two full weeks from Monday; Tuesdays missed
        status = "missed" if (d % 7) == 1 else "taken"
        events.append(
            ev(
                "DoseCheckin",
                {"status": status, "for_date": (T0 + timedelta(days=d)).date().isoformat()},
                day=d,
                source="telegram",
            )
        )
    as_of = T0 + timedelta(days=15)
    cards = build_rollup_cards(events, as_of, TOK)
    daily = [c for c in cards if c.kind == "daily"]
    weekly = [c for c in cards if c.kind == "weekly"]
    assert len(daily) == 15 and len(weekly) == 2
    w2 = weekly[1]
    assert w2.numbers["missed_7d"] == 1 and w2.numbers["taken_7d"] == 6
    assert "Tuesday" in w2.text and "1 not taken" in w2.text
    assert build_rollup_cards(events, as_of, TOK) == cards
    # future events never leak: cards for an earlier as_of are a prefix
    early = build_rollup_cards(events, T0 + timedelta(days=4), TOK)
    assert [c.text for c in early] == [
        c.text for c in cards if c.window_end < T0 + timedelta(days=4)
    ]
