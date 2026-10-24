import json
from datetime import date

from cm.agents.narrator import evidence_for, write_card
from cm.core.budget import TemplateOnlyMode
from cm.memory.features import compute_features
from cm.validator.banned_terms import find_banned_terms
from cm.validator.cite_or_cut import Evidence, cite_or_cut
from tests.unit.ai.conftest import AS_OF, FakeChat


def feats(events):
    return compute_features(events, AS_OF, day0=date(2026, 8, 27))


def reply(*sentences):
    return json.dumps({"sentences": list(sentences)})


def test_uncited_sentence_cut(events):
    f = feats(events)
    c = f.cites["missed_7d"][0]
    m = FakeChat(script=[reply(f"Missed 2 doses in 7 days [{c}].", "Looks worse lately.")])
    card = write_card(f, m)
    assert card.source == "model" and len(card.sentences) == 1
    assert ("Looks worse lately.", "no_ref") in card.cut


def test_wrong_number_cut(events):
    f = feats(events)
    c = f.cites["missed_7d"][0]
    m = FakeChat(script=[reply(f"Missed 9 doses in 7 days [{c}].", f"Missed 2 doses in 7 days [{c}].")])
    card = write_card(f, m)
    assert card.sentences == [f"Missed 2 doses in 7 days [{c}]."]
    assert card.cut[0][1] == "number_mismatch"


def test_all_cut_falls_back_to_template(events):
    f = feats(events)
    card = write_card(f, FakeChat(script=[reply("No cite here.", "Fake [E-deadbeef].")]))
    assert card.source == "template" and card.reason == "all_cut" and len(card.cut) == 2


def test_garbage_output_and_red_use_template(events):
    f = feats(events)
    assert write_card(f, FakeChat(script=["not json"])).reason == "bad_model_output"

    class Red:
        gov = None

        def invoke(self, *a, **k):
            raise TemplateOnlyMode("RED")

    assert write_card(f, Red()).reason == "budget_red"


def test_citations_resolve_to_real_events_and_template_is_valid(events):
    f = feats(events)
    real = {"E-" + str(e["event_id"]).replace("-", "")[:8] for e in events}
    card = write_card(f, FakeChat(script=["bad"]))
    res = cite_or_cut(card.sentences, evidence_for(f))
    assert not res.cut and res.kept
    from cm.validator.cite_or_cut import refs_of

    for s in card.sentences:
        for r in refs_of(s):
            assert r in real or r.startswith("B-")
    assert not find_banned_terms(card.text)


def test_banned_term_sentence_cut(events):
    f = feats(events)
    c = f.cites["missed_7d"][0]
    card = write_card(f, FakeChat(script=[reply(f"Missed 2 doses of rifampicin [{c}].", f"Missed 2 doses [{c}].")]))
    assert len(card.sentences) == 1 and card.cut[0][1] == "banned_term"


def test_cite_or_cut_unit():
    ev = Evidence.of({"E-1"}, {3})
    assert cite_or_cut("Seen 3 times [E-1]. Seen 4 times [E-1]. Bare.", ev).kept == ["Seen 3 times [E-1]."]
