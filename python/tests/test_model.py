from decimal import Decimal as D

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import ri_layercake as lc
from ri_layercake import gallery

M = D(1_000_000)


def test_builder_matches_shorthand():
    built = lc.Tower(units="m").add_retention(10).add_xl(40, 10).add_xl(50, 50, placed=0.75)
    assert built == lc.Tower.from_text("10 ret, 40 xs 10, 50 xs 50 @ 75%")


def test_edits_return_new_towers():
    t = lc.Tower.from_text("40 xs 10")
    t2 = t.update("L1", limit=50)
    assert t.layers[0].limit == 40 * M and t2.layers[0].limit == 50 * M


def test_split_and_merge():
    t = lc.Tower.from_text("100 xs 100 prem 10")
    s = t.split("L1", 150)
    assert [(l.attachment / M, l.limit / M, l.premium / M) for l in s.layers] == [(100, 50, 5), (150, 50, 5)]
    m = s.merge("L1", "L2")
    (l,) = m.layers
    assert (l.attachment, l.limit, l.premium) == (100 * M, 100 * M, 10 * M)
    with pytest.raises(ValueError):
        t.split("L1", 300)


def test_remove_and_next_id():
    t = lc.Tower.from_text("40 xs 10, 50 xs 50").remove("L1").add_xl(10, 100)
    assert [l.id for l in t.layers] == ["L2", "L3"]


def test_amount_strings():
    t = lc.Tower(units="m")
    assert t.amount("500k") == 500_000
    assert t.amount(2.5) == D("2500000")


def test_json_round_trip_gallery():
    for name in gallery.names():
        t = gallery.load(name)
        assert lc.Tower.from_json(t.to_json()) == t
        assert '"schema": "ri-layercake/tower@1"' in t.to_json(indent=1)


def test_to_code_runs_and_rebuilds():
    t = gallery.load("property_cat").accept("x")
    ns: dict = {}
    exec(t.to_code().split("\nview")[0], ns)  # noqa: S102
    assert ns["tower"] == t


def test_table_has_totals():
    t = lc.Tower.from_text("10 ret, 40 xs 10 prem 4, 50 xs 50 prem 3")
    from ri_layercake.table import table_data

    td = table_data(t)
    assert td.rows[0][0] == "Layer 2"
    assert td.totals == ["Total", "90", "", "", "", "7", "", "", ""]


# ---------------------------------------------------------------- properties

amounts = st.integers(min_value=1, max_value=5000).map(lambda n: D(n) / 10)
shares = st.integers(min_value=1, max_value=100).map(lambda n: D(n) / 100)


@st.composite
def towers(draw):
    t = lc.Tower(units=draw(st.sampled_from(["k", "m", "bn"])))
    att = D(0)
    if draw(st.booleans()):
        ret = draw(amounts)
        t = t.add_retention(ret)
        att = ret
    for _ in range(draw(st.integers(1, 6))):
        lim = draw(amounts)
        gap = draw(st.sampled_from([D(0), D(0), draw(amounts)]))
        t = t.add_xl(lim, att + gap, placed=draw(shares))
        att += gap + lim
    return t


@settings(max_examples=150, deadline=None)
@given(towers())
def test_text_round_trip(t):
    assert lc.Tower.from_text(t.to_text()) == t


@settings(max_examples=150, deadline=None)
@given(towers())
def test_json_round_trip(t):
    assert lc.Tower.from_json(t.to_json()) == t


@settings(max_examples=150, deadline=None)
@given(towers(), st.integers(min_value=0, max_value=60000).map(lambda n: D(n) / 10))
def test_losses_sum_to_loss(t, x):
    r = t.drop_loss(x)
    assert r.retained + r.recovered + r.uncovered == t.amount(x)
