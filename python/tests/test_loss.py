from decimal import Decimal as D

import ri_layercake as lc
from ri_layercake.loss import layer_loss, reinstatement_premium
from ri_layercake.model import Layer, Reinstatements

M = D(1_000_000)


def test_worked_example_from_spec():
    """10 ret, 40 xs 10, 50 xs 50 @ 75% and a loss of 75 (section 13)."""
    t = lc.Tower.from_text("10 ret, 40 xs 10, 50 xs 50 @ 75%")
    r = t.drop_loss(75)
    l1, l2 = r.layers
    assert (l1.recovery_100, l1.placed, l1.recovery_placed, l1.exhausted) == (40 * M, 1, 40 * M, True)
    assert (l2.recovery_100, l2.placed, l2.recovery_placed, l2.exhausted) == (25 * M, D("0.75"), D("18.75") * M, False)
    assert r.retention == 10 * M
    assert r.unplaced == D("6.25") * M
    assert r.retained == D("16.25") * M
    assert r.retained + r.recovered == 75 * M
    assert r.uncovered == 0


def test_exhaust_point():
    l = Layer("L1", "xl", 50 * M, 50 * M)
    assert l.exhaust == 100 * M


def test_rate_on_line_and_payback():
    t = lc.Tower.from_text("50 xs 50 prem 5")
    l = t.layers[0]
    assert l.rate_on_line == D("0.1")
    assert l.limit / l.effective_premium == 10  # payback in years


def test_layer_loss_bounds():
    l = Layer("L1", "xl", 50 * M, 50 * M)
    assert layer_loss(l, 30 * M) == 0
    assert layer_loss(l, 75 * M) == 25 * M
    assert layer_loss(l, 500 * M) == 50 * M


def test_reinstatement_premium_pro_rata_to_amount():
    l = Layer("L1", "xl", 50 * M, 50 * M, premium=5 * M, reinstatements=Reinstatements(1, 1.0))
    assert reinstatement_premium(l, 25 * M) == D("2.5") * M  # half the limit used
    assert reinstatement_premium(l, 50 * M) == 5 * M
    half = Layer("L1", "xl", 50 * M, 50 * M, premium=5 * M, reinstatements=Reinstatements(1, 0.5))
    assert reinstatement_premium(half, 50 * M) == D("2.5") * M


def test_reinstatement_premium_capped_by_count():
    l = Layer("L1", "xl", 10 * M, 0 * M, premium=2 * M, reinstatements=Reinstatements(0, 1.0))
    assert reinstatement_premium(l, 10 * M) == 0
    unl = Layer("L1", "xl", 10 * M, 0 * M, premium=2 * M, reinstatements=Reinstatements(None, 1.0))
    assert reinstatement_premium(unl, 10 * M) == 2 * M


def test_loss_above_top_and_in_gaps_is_uncovered():
    t = lc.Tower.from_text("10 ret, 40 xs 10, 50 xs 70")
    r = t.drop_loss(150)
    assert r.uncovered == (20 + 30) * M  # gap 50-70 plus 120-150 above the top
    assert r.retained + r.recovered + r.uncovered == 150 * M


def test_placed_basis_reinstatement_in_drop_loss():
    t = lc.Tower.from_text("50 xs 50 @ 50% 1 @ 100% prem 4")
    r = t.drop_loss(100)
    assert r.layers[0].reinstatement_premium == 2 * M  # 100% basis 4 x 50% placed
