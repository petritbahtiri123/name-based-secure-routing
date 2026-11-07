from scripts.check_normal_roster_kar import check


def test_retained_normal_roster_kars_match_python_composed_gate():
    assert check()["verified_KARs"] == 5
