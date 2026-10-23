"""Real-shaped pastes in tests/corpus/ against expected.json."""

import json
from decimal import Decimal as D
from pathlib import Path

import pytest

import ri_layercake as lc

CORPUS = Path(__file__).parent / "corpus"
EXPECTED = json.loads((CORPUS / "expected.json").read_text())


def approx(v):
    return None if v is None else D(str(v))


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_corpus(name):
    exp = EXPECTED[name]
    text = (CORPUS / name).read_text()
    t = lc.Tower.from_paste(text)
    errors = [d for d in t.diagnostics if d.severity == "error"]
    assert not errors, errors
    assert t.units == exp["units"]
    assert t.currency == exp["currency"]
    got = [(l.limit / t.factor, l.attachment / t.factor, l.placed) for l in t.xl_layers]
    want = [(approx(a), approx(b), approx(c)) for a, b, c in exp["layers"]]
    assert got == want
    ret = t.retention.limit / t.factor if t.retention else None
    assert ret == approx(exp["retention"])
    if "premiums" in exp:
        prem = [None if l.effective_premium is None else l.effective_premium / t.factor for l in t.xl_layers]
        assert prem == [approx(p) for p in exp["premiums"]]


def test_corpus_size():
    assert len(EXPECTED) >= 30
