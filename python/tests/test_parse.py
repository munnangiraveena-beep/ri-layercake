from decimal import Decimal as D

import pytest

import ri_layercake as lc

M = D(1_000_000)


def xl(t):
    return [(l.limit / t.factor, l.attachment / t.factor, l.placed) for l in t.xl_layers]


@pytest.mark.parametrize(
    "text, layers, retention",
    [
        ("10 ret, 40 xs 10, 50 xs 50", [(40, 10, 1), (50, 50, 1)], 10),
        ("50 xs 50 @ 75%", [(50, 50, D("0.75"))], None),
        ("40% part of 50 xs 50", [(50, 50, D("0.4"))], None),
        ("retention 5; 20 xs 5\n25 xs 25", [(20, 5, 1), (25, 25, 1)], 5),
        ("50 XS 50 @ 75% PLACED", [(50, 50, D("0.75"))], None),
        ("1,000 xs 500", [(1000, 500, 1)], None),
    ],
)
def test_grammar_examples(text, layers, retention):
    t = lc.Tower.from_text(text)
    assert not [d for d in t.diagnostics if d.severity == "error"]
    assert xl(t) == layers
    assert (t.retention.limit / t.factor if t.retention else None) == retention


def test_named_layer_with_reinstatement_and_premium():
    t = lc.Tower.from_text("Cat 3: 100 xs 100, 1 @ 100%, prem 4.2")
    l = t.layers[0]
    assert l.name == "Cat 3"
    assert l.reinstatements == lc.Reinstatements(1, 1.0)
    assert l.premium == D("4.2") * M


def test_rol_derives_premium():
    t = lc.Tower.from_text("£25m xs £5m rol 12%")
    assert t.layers[0].effective_premium == 3 * M
    assert t.currency == "GBP" and t.units == "m"


def test_thousands_separator_only_in_three_digit_groups():
    t = lc.Tower.from_text("40,10")
    assert [d.code for d in t.diagnostics] == ["parse", "parse"]


def test_unparseable_fragment_kept_with_span():
    text = "40 xs 10, banana, 50 xs 50"
    t = lc.Tower.from_text(text)
    (d,) = t.diagnostics
    assert d.code == "parse" and d.severity == "error"
    assert text[d.span[0]:d.span[1]] == "banana"
    assert len(t.layers) == 2


def test_units_set_by_first_unit_and_mixed_note():
    t = lc.Tower.from_text("500k xs 500k, 1m xs 1m")
    assert t.units == "k"
    assert t.xl_layers[1].limit == M
    assert any(d.code == "units_mixed" for d in t.diagnostics)


def test_bare_numbers_take_tower_unit():
    t = lc.Tower.from_text("40 xs 10", units="k")
    assert t.layers[0].limit == 40_000


def test_unlimited_reinstatements():
    t = lc.Tower.from_text("10 xs 10 unl @ 100%")
    assert t.layers[0].reinstatements.count is None


def test_never_raises_on_garbage():
    for text in ["", "xs", "@@@", "ret", "10 xs", "%%% part of", "Cat: ", "\n\n,,;"]:
        lc.Tower.from_text(text)


def test_to_text_round_trip_examples():
    for text in ["10 ret, 40 xs 10, 50 xs 50 @ 75%", "Cat 3: 100 xs 100 1 @ 100% prem 4.2", "25 xs 5 rol 12%"]:
        t = lc.Tower.from_text(text)
        assert lc.Tower.from_text(t.to_text()) == t


# ---------------------------------------------------------------- paste parser

def test_tsv_with_headers_and_units_in_header():
    paste = "Layer\tLimit (£m)\tExcess (£m)\t% Placed\tPremium (£m)\n1\t40\t10\t100%\t4\n2\t50\t50\t75%\t3\n"
    t = lc.Tower.from_paste(paste)
    assert xl(t) == [(40, 10, 1), (50, 50, D("0.75"))]
    assert t.xl_layers[1].premium == 3 * M


def test_headerless_infers_attachment_by_chaining():
    paste = "10\t40\n50\t50\n100\t150\n"  # attachment first, limit second
    t = lc.Tower.from_paste(paste)
    assert xl(t) == [(40, 10, 1), (50, 50, 1), (150, 100, 1)]


def test_combined_column_goes_through_shorthand():
    paste = "Layer\tShare\n40 xs 10\t100%\n50 xs 50\t60%\n"
    t = lc.Tower.from_paste(paste)
    assert xl(t) == [(40, 10, 1), (50, 50, D("0.6"))]


def test_html_table_cells_only():
    html = ("<table><tr><th>Limit</th><th>Attachment</th></tr>"
            "<tr><td>40<script>x</script></td><td>10</td></tr></table>")
    t = lc.Tower.from_paste(html)
    assert len(t.layers) == 1


def test_paste_of_shorthand_lines():
    t = lc.Tower.from_paste("10 ret\n40 xs 10\n50 xs 50")
    assert len(t.layers) == 3


def test_mapping_override():
    from ri_layercake.parse import parse_rows

    rows = [["A", "B"], ["40", "10"], ["50", "50"]]
    t = parse_rows(rows, mapping={"header_row": 0, "columns": {"0": "limit", "1": "attachment"}})
    assert xl(t) == [(40, 10, 1), (50, 50, 1)]
