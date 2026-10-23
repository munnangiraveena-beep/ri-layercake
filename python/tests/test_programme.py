"""Quota share, stop loss, commercial terms, coverage and the premium walk."""

from decimal import Decimal as D

import pytest

import ri_layercake as lc
from ri_layercake import formulas as f
from ri_layercake.model import SlidingScale, Terms

M = D(1_000_000)


def by_id(result, lid):
    return next(l for l in result.layers if l.layer == lid)


# ---------------------------------------------------------------- formulas

def test_rol_premium_adj_rate_relationships():
    t = lc.Tower.from_text("epi 200, 50 xs 50 rate 2%")
    l = t.layers[0]
    assert f.premium(t, l) == 4 * M  # Premium (RTE) = EPI x Adj. rate
    assert f.rol(t, l) == D("0.08")  # ROL = Premium / Layer limit
    assert f.adj_rate(t, l) == f.rol(t, l) * l.limit / t.epi  # Adj. rate = ROL x Limit / EPI
    t2 = lc.Tower.from_text("epi 200, 50 xs 50 rol 8%")
    assert f.adj_rate(t2, t2.layers[0]) == D("0.02")


def test_agg_limit():
    t = lc.Tower.from_text("50 xs 50 2 @ 100%, 20 xs 100 unl @ 100%, 10 xs 120")
    a, b, c = t.layers
    assert f.agg_limit(t, a) == 150 * M  # Limit x (1 + 2)
    assert f.agg_limit(t, b).is_infinite()
    assert f.agg_limit(t, c) == 10 * M


def test_qs_premium_is_cession_of_epi():
    t = lc.Tower.from_text("epi 120, qs 20% limit 50")
    assert f.premium(t, t.qs) == 24 * M


# ---------------------------------------------------------------- coverage per risk

def test_qs_stacked_example_from_the_user():
    """QS 20%, exposure 50: QS cedes 10, the remaining 40 passes through all XL layers."""
    t = lc.Tower.from_text("qs 20% limit 100, 5 xs 5, 10 xs 10, 30 xs 20")
    r = t.drop_loss(50)
    assert r.qs_ceded == 10 * M and r.net_of_qs == 40 * M
    assert [by_id(r, i).recovery_100 / M for i in ("L1", "L2", "L3")] == [5, 10, 20]
    assert r.retention == 5 * M
    assert r.retained + r.recovered + r.uncovered == 50 * M


def test_qs_side_by_side_scales_attachment_and_limit():
    """Side by side: XL attachment and limit x (1 - c), on the net retained."""
    t = lc.Tower.from_text("qs 20% limit 100, 40 xs 10").programme(arrangement="side_by_side")
    r = t.drop_loss(50)
    l1 = by_id(r, "L1")
    assert l1.limit_used == 32 * M  # 40 x 0.8
    assert l1.recovery_100 == 32 * M  # net 40, attaches at 8, limit 32
    assert r.qs_ceded == 10 * M


def test_qs_limit_caps_cession():
    t = lc.Tower.from_text("qs 20% limit 25, 100 xs 50")
    r = t.drop_loss(100)
    assert r.qs_ceded == 5 * M and r.net_of_qs == 95 * M
    assert by_id(r, "L1").recovery_100 == 45 * M


def test_order_times_placed():
    t = lc.Tower.from_text("40 xs 10 @ 50% order 80%")
    r = t.drop_loss(50)
    assert by_id(r, "L1").placed == D("0.4")
    assert by_id(r, "L1").recovery_placed == 16 * M


def test_trapped_exposure_is_median():
    t = lc.Tower.from_text("40 xs 10")
    for e, want in [(5, 0), (30, 20), (80, 40)]:
        assert by_id(t.drop_loss(e), "L1").recovery_100 == want * M


def test_portfolio_trapped_exposure():
    t = lc.Tower.from_text("10 ret, 40 xs 10, 50 xs 50")
    p = t.portfolio([("A", 5), ("B", 30), ("C", 120)])
    summary = {row["layer"]: row for row in p.to_dict()["layers"]}
    assert summary["L1"]["trapped"] == "60" and summary["L1"]["risks_reaching"] == 2
    assert summary["L2"]["trapped"] == "50" and summary["L2"]["risks_exhausting"] == 1


def test_portfolio_from_paste():
    t = lc.Tower.from_text("40 xs 10")
    p = t.portfolio("Risk\tSum insured\nA\t5\nB\t30\nC\t80\n")
    assert p.to_dict()["count"] == 3


# ---------------------------------------------------------------- stop loss and terms

def test_stop_loss_on_loss_ratio_net_of_qs():
    t = lc.Tower.from_text("epi 100, qs 20% limit 50, sl 20% xs 80%, sl 20% xs 100%")
    a = t.aggregate(125)  # net of QS 100: loss ratio 100%
    assert a.net_of_qs == 100 * M and a.loss_ratio == 1
    taken = [s.recovery_100 / M for s in a.stop_loss]
    assert taken == [20, 0]


def test_qs_agg_limit_caps_aggregate_cession():
    t = lc.Tower.from_text("epi 100, qs 50% limit 50 agg 30")
    assert t.aggregate(100).qs_ceded == 30 * M


def test_sliding_scale_and_profit_commission():
    ss = SlidingScale(min=D("0.25"), max=D("0.35"), lr_low=D("0.5"), lr_high=D("0.7"))
    assert ss.rate(D("0.4")) == D("0.35") and ss.rate(D("0.8")) == D("0.25")
    assert ss.rate(D("0.6")) == D("0.30")
    t = lc.Tower.from_text("epi 100, qs 20% limit 50").update(
        "Q1", terms=Terms(sliding_scale=ss, profit_commission=D("0.2"), management_expenses=D("0.05")))
    res = f.qs_result(t, 10 * M)  # QS premium 20, ceded loss 10: loss ratio 50%
    assert res["commission_rate"] == D("0.35") and res["commission"] == 7 * M
    assert res["management_expenses"] == 1 * M
    assert res["profit"] == 2 * M and res["profit_commission"] == D("0.4") * M


def test_no_claims_bonus():
    t = lc.Tower.from_text("epi 100, 10 xs 10 prem 2 ncb 10%")
    assert f.no_claims_bonus(t, t.layers[0]) == D("0.2") * M
    assert by_id(t.drop_loss(15), "L1").ncb_lost


# ---------------------------------------------------------------- validators

def codes(t):
    return {d.code for d in t.validate()}


def test_qs_validators():
    t = lc.Tower.from_text("epi 100, qs 20% limit 80 agg 10")
    assert {"qs_limit_crm", "qs_agg_limit"} <= codes(t)
    over = t.programme(counterparty_limit=50)
    d = next(d for d in over.validate() if d.code == "qs_limit_crm")
    assert d.severity == "warning"
    assert over.apply(d.fixes[0]).qs.limit == 50 * M
    low = next(d for d in t.validate() if d.code == "qs_agg_limit")
    assert low.severity == "warning"


def test_epi_needed_for_stop_loss_and_adj_rate():
    assert "epi_missing" in codes(lc.Tower.from_text("sl 20% xs 80%"))
    assert "epi_missing" in codes(lc.Tower.from_text("50 xs 50 rate 2%"))


def test_pricing_mismatch_across_three_inputs():
    t = lc.Tower.from_text("epi 100, 50 xs 50 prem 5 rate 4%")
    (d,) = [d for d in t.validate() if d.code == "rol_mismatch"]
    assert [x.label for x in d.fixes] == ["Use premium", "Use adjusted rate"]


def test_one_quota_share():
    with pytest.raises(ValueError):
        lc.Tower.from_text("qs 20% limit 50").add_qs(0.3, 50)


# ---------------------------------------------------------------- premium walk

def test_premium_walk():
    t = lc.Tower.from_text("epi 100, qs 20% limit 50 comm 30%, 10 xs 10 prem 4 el 2 ncb 10% 1 @ 100%").programme(
        internal_expenses=0.1, expected_loss_ratio=0.6, brokerage_xl=0.1, tax=0.02)
    w = t.premium_walk()
    s = {x.key: x.amount / M for x in w.steps}
    assert s["internal_expenses"] == -10
    assert s["qs_premium"] == -20
    assert s["xl_premium"] == -4
    assert s["reinstatement_premium"] == D("-0.8")  # 1 x 4 x 2 / 10
    assert s["expected_loss"] == -60
    assert s["el_saved_qs"] == 12
    assert s["el_saved_xl"] == 2
    assert s["qs_commission"] == 6
    assert s["no_claims_bonus"] == D("0.4")
    assert s["brokerage"] == D("-0.9")  # 2.5% x QS premium 20 (default) + 10% x XL premium 4
    assert s["tax"] == D("-0.48")
    assert w.result / M == 100 - 10 - 20 - 4 - D("0.8") - 60 + 12 + 2 + 6 + 0 + D("0.4") - D("0.9") - D("0.48")
    assert w.margin == w.result / t.epi


def test_walk_needs_epi():
    with pytest.raises(ValueError):
        lc.Tower.from_text("40 xs 10").premium_walk()


def test_json_round_trip_full_programme():
    t = lc.Tower.from_text("epi 100, qs 20% limit 50 agg 300 comm 30%, 10 xs 10 ncb 10% el 2, sl 20% xs 80%").programme(
        arrangement="side_by_side", counterparty_limit=60, internal_expenses=0.1, brokerage_xl=0.1)
    t = t.update("Q1", terms=Terms(commission=D("0.3"), profit_commission=D("0.2"), management_expenses=D("0.05"),
                                   sliding_scale=SlidingScale(D("0.25"), D("0.35"), D("0.5"), D("0.7"))))
    assert lc.Tower.from_json(t.to_json()) == t


def test_walk_market_defaults():
    """Internal expenses 30% of EPI, brokerage 10% of XL and 2.5% of QS premium, unless set."""
    t = lc.Tower.from_text("epi 100, qs 20% limit 50, 10 xs 10 prem 4").programme(expected_loss_ratio=0.6)
    steps = {s.key: s for s in t.premium_walk().steps}
    assert steps["internal_expenses"].amount == -30 * M and steps["internal_expenses"].default
    assert steps["brokerage"].amount == -(D("0.5") + D("0.4")) * M and steps["brokerage"].default
    custom = t.programme(internal_expenses=0.25, brokerage_qs=0.03, brokerage_xl=0.12)
    steps = {s.key: s for s in custom.premium_walk().steps}
    assert steps["internal_expenses"].amount == -25 * M and not steps["internal_expenses"].default
    assert steps["brokerage"].amount == -(D("0.6") + D("0.48")) * M


def test_before_and_after_reinsurance():
    t = gallery_tower = __import__("ri_layercake").gallery.load("credit_surety")
    w = t.premium_walk()
    ba = w.before_after()
    assert ba["after"]["result"] == w.result
    assert ba["before"]["result"] == w.result_without_reinsurance
    assert ba["before"]["loss_ratio"] == t.expected_loss_ratio
    assert ba["before"]["margin"] == w.result_without_reinsurance / t.epi
    assert ba["after"]["premium"] < ba["before"]["premium"]
    del gallery_tower


def test_lines_with_variable_qs():
    t = (lc.Tower.from_text("qs 20% limit 25, 15 xs 5")
         .add_line("Credit", 200, expected_loss_ratio=0.5, cession=0.2)
         .add_line("Surety", 60, expected_loss_ratio=0.45, cession=0.3))
    assert t.epi == 260 * M and t.expected_loss_ratio == D("127") / D("260")
    assert f.premium(t, t.qs) == 58 * M
    assert f.qs_ceded_el(t) == D("28.1") * M
    assert t.exposure(20, "Credit").qs_ceded == 4 * M
    assert t.exposure(20, "Surety").qs_ceded == 6 * M
    side = t.programme(arrangement="side_by_side")
    assert by_id(side.exposure(20, "Surety"), "L1").limit_used == D("10.5") * M  # 15 x (1 - 30%)
    assert lc.Tower.from_json(t.to_json()) == t
    assert t.remove_line("Surety").update_line("Credit", cession=0.25).line("Credit").cession == D("0.25")
