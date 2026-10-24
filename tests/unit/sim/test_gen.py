from cm.sim.gen import generate_patients, instant_for
from cm.sim.truth import load_truth, write_truth


def test_same_seed_identical():
    assert generate_patients(2042, 10, 60) == generate_patients(2042, 10, 60)


def test_different_seed_differs():
    assert generate_patients(1, 10, 60) != generate_patients(2, 10, 60)


def test_shape_and_truth_roundtrip(tmp_path):
    ps = generate_patients(7, 5, 60)
    assert len(ps) == 5 and len(ps[0].taken) == 74 and ps[0].reported[60] is None
    write_truth(tmp_path / "t.json", ps)
    assert set(load_truth(str(tmp_path / "t.json"))) == {p.token for p in ps}


def test_sim_clock_instants_increase():
    assert instant_for(3) < instant_for(60)
