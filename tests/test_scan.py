import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scan  # noqa: E402

ANGLES = list(range(20, 161, 10))


def room(dips=None):
    r = {a: 250 for a in ANGLES}
    for angle_set, dist in (dips or []):
        for a in angle_set:
            r[a] = dist
    return [(a, r[a]) for a in ANGLES]


def test_empty_room_is_clear():
    res = scan.analyse(room())
    assert res.contacts == []
    assert res.people_estimate == 0
    assert res.threat == "CLEAR"
    assert res.nearest is None


def test_one_dip_left_is_few():
    res = scan.analyse(room([((30, 40, 50), 120)]))
    assert len(res.contacts) == 1
    c = res.contacts[0]
    assert c.side == "left"
    assert c.people == 1
    assert res.threat == "FEW"
    assert res.nearest is c


def test_three_dips_is_crowd():
    # dips are 2 angles wide so most of the sweep is still wall and the median reference holds
    res = scan.analyse(room([((30, 40), 120), ((80, 90), 150), ((140, 150), 110)]))
    assert len(res.contacts) == 3
    assert res.people_estimate == 3
    assert res.threat == "CROWD"


def test_adjacent_dips_with_distance_gap_do_not_merge():
    # two runs two angles apart, distances 100 and 180 differ by 80 > MERGE_MAX_DIST_DIFF_CM
    # (a single missing angle gets filled by the 3-point median smoothing, by design)
    res = scan.analyse(room([((30, 40, 50), 100), ((80, 90, 100), 180)]))
    assert len(res.contacts) == 2


def test_adjacent_dips_with_similar_distance_merge():
    res = scan.analyse(room([((40, 50, 60), 100), ((80, 90, 100), 120)]))
    assert len(res.contacts) == 1


def test_zero_readings_are_open_space():
    r = room([((30, 40, 50), 120)])
    r = [(a, 0 if a in (80, 90, 100) else cm) for a, cm in r]
    res = scan.analyse(r)
    assert len(res.contacts) == 1
    assert res.contacts[0].side == "left"


def test_mirror_swaps_sides():
    normal = scan.analyse(room([((30, 40, 50), 120)]), mirror=False)
    mirrored = scan.analyse(room([((30, 40, 50), 120)]), mirror=True)
    assert normal.contacts[0].side == "left"
    assert mirrored.contacts[0].side == "right"
