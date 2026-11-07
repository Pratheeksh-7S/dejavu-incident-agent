import pytest

import agent


def make_incidents(n_proven, n_failed=0):
    incs = {}
    for i in range(n_proven):
        incs[100 + i] = {"id": 100 + i, "fix_successful": True}
    for i in range(n_failed):
        incs[200 + i] = {"id": 200 + i, "fix_successful": False}
    return incs


@pytest.fixture
def patch_incidents(monkeypatch):
    def _patch(incs):
        monkeypatch.setattr(agent, "get_incident", lambda iid: incs.get(iid))
    return _patch


def answer_for(incs, model_conf):
    return {"confidence": model_conf, "evidence": [{"incident_id": i, "why": "x"} for i in incs]}


@pytest.mark.parametrize("n", [3, 4, 5, 8])
@pytest.mark.parametrize("model_conf", [0, 50, 95])
def test_three_or_more_proven_gives_90_to_98(patch_incidents, n, model_conf):
    incs = make_incidents(n)
    patch_incidents(incs)
    conf, basis = agent.calibrate(answer_for(incs, model_conf))
    assert 90 <= conf <= 98
    assert basis == f"{n} of {n} matching past incidents were fixed this way"


@pytest.mark.parametrize("model_conf", [0, 40, 80, 99])
def test_two_proven_gives_75_to_89(patch_incidents, model_conf):
    incs = make_incidents(2)
    patch_incidents(incs)
    conf, _ = agent.calibrate(answer_for(incs, model_conf))
    assert 75 <= conf <= 89


@pytest.mark.parametrize("model_conf", [0, 40, 60, 99])
def test_one_proven_gives_55_to_74(patch_incidents, model_conf):
    incs = make_incidents(1)
    patch_incidents(incs)
    conf, _ = agent.calibrate(answer_for(incs, model_conf))
    assert 55 <= conf <= 74


@pytest.mark.parametrize("model_conf", [0, 30, 90, 100])
def test_no_proven_match_is_capped_at_30(patch_incidents, model_conf):
    incs = make_incidents(0, n_failed=2)
    patch_incidents(incs)
    conf, basis = agent.calibrate(answer_for(incs, model_conf))
    assert conf <= 30
    assert basis == "0 of 2 matching past incidents were fixed this way"


def test_failed_fixes_do_not_count_as_proven(patch_incidents):
    incs = make_incidents(2, n_failed=3)
    patch_incidents(incs)
    conf, basis = agent.calibrate(answer_for(incs, 99))
    assert 75 <= conf <= 89
    assert basis.startswith("2 of 5")


@pytest.mark.parametrize("evidence", [[], None])
def test_empty_evidence_says_no_matching_incident(patch_incidents, evidence):
    patch_incidents({})
    answer = {"confidence": 95}
    if evidence is not None:
        answer["evidence"] = evidence
    conf, basis = agent.calibrate(answer)
    assert basis == "No matching incident in memory"
    assert conf <= 30


def test_unknown_incident_ids_are_ignored(patch_incidents):
    patch_incidents({})
    conf, basis = agent.calibrate({"confidence": 90, "evidence": [{"incident_id": 999}]})
    assert basis == "No matching incident in memory"
    assert conf <= 30


def test_confidence_never_exceeds_98_even_if_model_says_100(patch_incidents):
    incs = make_incidents(3)
    patch_incidents(incs)
    conf, _ = agent.calibrate(answer_for(incs, 100))
    assert conf <= 98
