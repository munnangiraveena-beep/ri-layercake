"""Risk view: simulated years with attritional and large losses; loss ratio, margin, capital and RoC."""

import pytest

import ri_layercake as lc
from ri_layercake import gallery, risk

S = risk.RiskSettings(sims=20_000, seed=3)
EXAMPLES = ["per_risk_xol", "qs_xl_stacked", "qs_xl_side_by_side", "credit_surety", "credit_qs_xl", "surety_xl",
            "full_programme", "stop_loss"]


def metrics(name):
    t = gallery.load(name)
    sim = risk.simulate(t, S)
    return t, sim, risk.gross(sim), risk.evaluate(sim)


def test_large_losses_calibrate_to_the_layer_els_entered():
    t, sim, _, _ = metrics("per_risk_xol")
    for layer in t.xl_layers:
        model = sim.model_layer_el[layer.id]
        assert model == pytest.approx(float(layer.terms.expected_loss), rel=0.08)


def test_simulated_expected_result_is_close_to_the_walk():
    t, sim, g, cur = metrics("per_risk_xol")
    walk = t.premium_walk()
    assert g.expected_result == pytest.approx(float(walk.result_without_reinsurance), rel=0.02)
    assert cur.expected_result == pytest.approx(float(walk.result), rel=0.05)


@pytest.mark.parametrize("name", EXAMPLES)
def test_every_example_is_placeable_and_reinsurance_does_what_it_should(name):
    """Loss ratio down, a better bad year, less capital and a higher return on capital; reinsurers keep a margin."""
    _, _, g, cur = metrics(name)
    assert cur.placeable
    assert cur.net_loss_ratio < g.net_loss_ratio
    assert cur.bad_year_margin > g.bad_year_margin
    assert cur.capital < g.capital
    assert cur.roc > g.roc
    # placeable reinsurance costs a little expected margin, never a lot
    assert g.margin - 0.07 < cur.margin < g.margin


def test_explore_finds_the_best_placeable_mix():
    t = gallery.load("credit_surety")
    ex = risk.explore(t, "qs:Credit", "qs:Surety", settings=S)
    d = ex.to_dict()
    assert max(d["x"]["values"]) == 0.5 and max(d["y"]["values"]) == 0.5
    best = d["grid"][d["best"][0]][d["best"][1]]
    assert best["placeable"]
    assert all(cell["roc"] <= best["roc"] for row in d["grid"] for cell in row if cell["placeable"] and cell["roc"])
    assert best["roc"] >= d["current"]["roc"]


def test_levers_change_the_programme_without_editing_it():
    t = gallery.load("per_risk_xol")
    sim = risk.simulate(t, S)
    base = risk.evaluate(sim)
    higher = risk.evaluate(sim, risk.Levers(xl_retention=4e6))  # retention 2m -> 4m
    assert higher.capital > base.capital  # keeps more risk
    cheap = risk.evaluate(sim, risk.Levers(xl_price=0.8))
    assert cheap.expected_result > base.expected_result
    q = gallery.load("qs_xl_stacked")
    qsim = risk.simulate(q, S)
    more = risk.evaluate(qsim, risk.Levers(cessions={"*": 0.4}))
    assert more.capital < risk.evaluate(qsim).capital
    generous = risk.evaluate(qsim, risk.Levers(commission_shift=0.05))
    assert not generous.placeable  # reinsurers would be left with under 3%


def test_too_high_a_cession_is_not_placeable():
    q = gallery.load("qs_xl_stacked")
    sim = risk.simulate(q, S)
    assert not risk.evaluate(sim, risk.Levers(cessions={"*": 0.9})).placeable


def test_stop_loss_attachment_lever():
    """A lower attachment with the same limit pays more often and costs more, but exhausts sooner in the tail."""
    t = gallery.load("stop_loss")
    sim = risk.simulate(t, S)
    base, low = risk.evaluate(sim), risk.evaluate(sim, risk.Levers(sl_attachment=0.75))
    assert low.net_loss_ratio < base.net_loss_ratio
    assert low.expected_result < base.expected_result


def test_needs_epi_and_el():
    with pytest.raises(ValueError):
        risk.risk_metrics(lc.Tower.from_text("40 xs 10"), S)


def test_apply_levers_writes_the_what_if_into_the_programme():
    t = gallery.load("full_programme")
    lv = risk.Levers(cessions={"*": 0.3}, commission_shift=0.01, xl_retention=3e6, xl_price=0.9, sl_attachment=0.5)
    new = risk.apply_levers(t, lv)
    assert float(new.qs.cession) == 0.3
    assert new.qs.terms.commission == t.qs.terms.commission + __import__("decimal").Decimal("0.01")
    first = sorted(new.xl_layers, key=lambda l: l.attachment)[0]
    old_first = sorted(t.xl_layers, key=lambda l: l.attachment)[0]
    assert float(first.attachment) == 3e6 and first.exhaust == old_first.exhaust
    assert float(new.retention.limit) == 3e6
    assert float(new.sl_layers[0].attachment) == 0.5
    sim = risk.simulate(t, S)
    expected = risk.evaluate(sim, lv)
    applied = risk.evaluate(risk.simulate(new, S))
    assert applied.capital == pytest.approx(expected.capital, rel=0.15)


def test_best_balances_loss_ratio_margin_and_roc():
    t = gallery.load("credit_surety")
    d = risk.explore(t, "qs:Credit", "qs:Surety", settings=S).to_dict()
    iy, ix = d["best"]
    assert d["efficient"][iy][ix]
    cells = [(a, b) for a in range(len(d["grid"])) for b in range(len(d["grid"][0]))]
    eff = [c for c in cells if d["efficient"][c[0]][c[1]]]
    assert 1 < len(eff) < len(cells)
    # nothing efficient is beaten on all three by another placeable programme
    for a, b in eff:
        m = d["grid"][a][b]
        for c, e in cells:
            o = d["grid"][c][e]
            if (c, e) != (a, b) and o["placeable"]:
                better = o["net_loss_ratio"] < m["net_loss_ratio"] and o["margin"] > m["margin"] and o["roc"] > m["roc"]
                assert not better
    assert all(d["score"][iy][ix] >= d["score"][a][b] for a, b in eff)


def test_weights_lean_the_choice():
    t = gallery.load("credit_surety")
    sim = risk.simulate(t, S)
    roc_only = risk.explore(t, "qs:Credit", "qs:Surety", settings=risk.RiskSettings(
        sims=S.sims, seed=S.seed, weight_loss_ratio=0, weight_margin=0, weight_roc=1), sim=sim).to_dict()
    margin_only = risk.explore(t, "qs:Credit", "qs:Surety", settings=risk.RiskSettings(
        sims=S.sims, seed=S.seed, weight_loss_ratio=0, weight_margin=1, weight_roc=0), sim=sim).to_dict()
    lr_only = risk.explore(t, "qs:Credit", "qs:Surety", settings=risk.RiskSettings(
        sims=S.sims, seed=S.seed, weight_loss_ratio=1, weight_margin=0, weight_roc=0), sim=sim).to_dict()
    best = lambda d: d["grid"][d["best"][0]][d["best"][1]]  # noqa: E731
    placeable = [m for row in roc_only["grid"] for m in row if m["placeable"]]
    assert best(roc_only)["roc"] == max(m["roc"] for m in placeable)
    assert best(margin_only)["margin"] == max(m["margin"] for m in placeable)
    assert best(lr_only)["net_loss_ratio"] == min(m["net_loss_ratio"] for m in placeable)


def test_stop_loss_below_the_expected_loss_ratio_is_not_placeable():
    t = gallery.load("full_programme")
    sim = risk.simulate(t, S)
    assert not risk.evaluate(sim, risk.Levers(sl_attachment=0.30)).placeable
    assert risk.evaluate(sim).placeable
