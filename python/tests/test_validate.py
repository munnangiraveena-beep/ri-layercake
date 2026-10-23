from decimal import Decimal as D

import ri_layercake as lc

M = D(1_000_000)


def codes(t, view=None):
    return [d.code for d in t.validate(view)]


def test_clean_tower_has_no_diagnostics():
    assert codes(lc.Tower.from_text("10 ret, 40 xs 10, 50 xs 50")) == []


def test_gap_and_fixes():
    t = lc.Tower.from_text("10 ret, 40 xs 10, 50 xs 60")
    (d,) = t.validate()
    assert d.code == "gap" and d.severity == "warning"
    assert [f.label for f in d.fixes] == ["Lower next attachment", "Extend layer below", "Leave as unreinsured"]
    lowered = t.apply(d.fixes[0])
    assert codes(lowered) == []
    assert lowered.layer("L2").attachment == 50 * M and lowered.layer("L2").exhaust == 110 * M
    extended = t.apply(d.fixes[1])
    assert codes(extended) == [] and extended.layer("L1").limit == 50 * M
    kept = t.apply(d.fixes[2])
    assert codes(kept) == []


def test_overlap_and_fixes():
    t = lc.Tower.from_text("40 xs 10, 50 xs 40")
    (d,) = t.validate()
    assert d.code == "overlap"
    raised = t.apply(d.fixes[0])
    assert codes(raised) == [] and raised.layer("L2").attachment == 50 * M
    assert codes(t.apply(d.fixes[-1])) == []


def test_share_over_and_under():
    t = lc.Tower.from_text("40 xs 10 @ 110%, 50 xs 50 @ 75%")
    ds = {d.code: d for d in t.validate()}
    assert ds["share_over"].severity == "warning"
    assert ds["share_under"].severity == "info"
    assert ds["share_under"].message == "Layer 2 is 75% placed"
    assert t.apply(ds["share_over"].fixes[0]).layer("L1").placed == 1


def test_non_positive_is_error():
    t = lc.Tower(units="m").add_xl(0, 10)
    assert codes(t) == ["non_positive"]
    assert t.validate()[0].severity == "error"


def test_rol_mismatch():
    t = lc.Tower.from_text("50 xs 50 prem 5 rol 12%")
    (d,) = t.validate()
    assert d.code == "rol_mismatch"
    assert t.apply(d.fixes[0]).layers[0].rol is None
    assert t.apply(d.fixes[1]).layers[0].premium is None
    assert codes(lc.Tower.from_text("50 xs 50 prem 5 rol 10.04%")) == []


def test_extreme_scale_only_in_linear_view():
    t = lc.Tower.from_text("1 xs 1, 100 xs 2")
    assert "extreme_scale" not in codes(t)
    assert "extreme_scale" in codes(t, lc.View(scale="linear"))


def test_fix_round_trips_through_dict():
    t = lc.Tower.from_text("40 xs 10, 50 xs 60")
    fix = t.validate()[0].fixes[0]
    assert lc.Fix.from_dict(fix.to_dict()).fields["attachment"] == str(50 * M)
    assert codes(t.apply(fix.to_dict())) == []
