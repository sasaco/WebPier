"""Independent VBScript Single oracles and moving-load edge conditions."""

import importlib

import pytest

from src.inputs import InputError


CURRENT = (0.45, 27, 0.375, 0.375, 25.2, 0.375)


def search(**overrides):
    args = dict(lengths=CURRENT, car_count=10, car_length=16.4,
                a1=4, a2=2, axle_load=170)
    args.update(overrides)
    return importlib.import_module("src.moving_load").search_reactions(**args)


@pytest.mark.parametrize(("args", "expected"), [
    # The decimal-joint long-span case is independently checked in
    # test_moving_load_boundary; its unchanged legacy result is retained there.
    ({}, (512.2037353515625, 507.7962951660156, 633.1151123046875, 386.8848876953125)),
    ({"axle_load": 34, "car_count": 1, "car_length": 12},
     (11.648147583007812, 56.35185241699219, 66.31349182128906, 1.6865081787109375)),
    ({"car_count": 1, "a2": 0},
     (75.71295928955078, 94.28704071044922, 172.52975463867188, -2.529754638671875)),
])
def test_exact_independent_single_oracles(args, expected):
    result = search(**args)
    assert result.reactions == expected
    assert len(result.positions) == len(result.contributions)
    assert result.candidate_count == len(result.axle_positions) * 7
    assert sum(result.reactions) == pytest.approx(len(result.positions) * args.get("axle_load", 170), abs=0.001)
    assert all(term.side in ("B", "C") for term in result.contributions)
    assert tuple(term.position for term in result.contributions) == result.positions


def test_joint_and_search_ties_preserve_first_candidate():
    result = search(lengths=(0, 10, 0, 0, 10, 0), axle_load=100,
                    car_count=1, car_length=12, a2=0)
    assert result.reactions == (80, 20, 100, 0)
    assert result.positions == (10, 2)
    assert result.axle_positions == (0, 8)
    assert result.selected_axle == 0
    assert result.selected_point == 4
    assert result.max_rb_rc == 120
    assert result.contributions[0].side == "C"
    assert result.contributions[1].side == "B"
    assert result.contributions[1].distance == 2


def test_four_axle_formation_is_sequential_single():
    result = search(car_count=2)
    assert result.axle_positions == (
        0, 2, 10.399999618530273, 12.399999618530273,
        16.399999618530273, 18.399999618530273,
        26.799999237060547, 28.799999237060547,
    )


def test_zero_load_has_no_selected_candidate():
    result = search(axle_load=0)
    assert result.reactions == (0, 0, 0, 0)
    assert result.positions == result.contributions == ()
    assert result.max_rb_rc == 0
    assert result.selected_axle is result.selected_point is None


def test_positive_load_without_positive_candidate_is_an_input_error():
    with pytest.raises(InputError):
        search(lengths=(0, 1e-5, 0, 0, 1e-5, 0), car_count=1)


def test_positive_load_that_underflows_single_is_an_input_error():
    with pytest.raises(InputError):
        search(axle_load=1e-50)


@pytest.mark.parametrize("args", [
    {"lengths": (0, 1)}, {"lengths": (0, 0, 0, 0, 10, 0)},
    {"lengths": (0, 10, 0, -1, 10, 0)},
    {"lengths": (0, float("inf"), 0, 0, 10, 0)},
    {"car_count": 0}, {"car_count": 201}, {"car_count": 1.5},
    {"car_count": True}, {"car_length": 8}, {"car_length": float("nan")},
    {"a1": 0}, {"a2": -1}, {"axle_load": -1}, {"axle_load": False},
    {"axle_load": 1e100}, {"car_length": "16.4"},
])
def test_invalid_input_rejected(args):
    with pytest.raises(InputError):
        search(**args)
