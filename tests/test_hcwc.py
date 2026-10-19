"""Contact distributions: table validation and the exceedance function (plan §5.7, T14–T17)."""
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

from posgridder.core.hcwc import (Exceedance, TableError, basis_from_filename, parse_csv,
                                  parse_hcwc_json, parse_pasted, validate_table)
from posgridder.core.operations import OperationError
from posgridder.io.hcwc_files import import_hcwc

FIX = Path(__file__).parent / "fixtures" / "hcwc_builder"
P = np.arange(100, -1, -1.0)


def uniform_table(lo: float, hi: float):
    """C ~ U(lo, hi): P100 at lo, P0 at hi."""
    return P, lo + (hi - lo) * (100 - P) / 100


def test_uniform_exceedance_is_exact():
    """T14: E(z) = (hi − z)/(hi − lo) inside, 1 above, 0 below."""
    e = Exceedance(*uniform_table(2100, 2200))
    z = np.linspace(2050, 2250, 401)
    np.testing.assert_allclose(e(z), np.clip((2200 - z) / 100, 0, 1), atol=1e-12)
    assert e(2150.0) == pytest.approx(0.5, abs=1e-12)
    assert float(e(2200.0)) == 0.0


@pytest.mark.parametrize("p, d, match", [
    (P[::-1], uniform_table(2100, 2200)[1][::-1], "run upwards"),
    (P, uniform_table(2100, 2200)[1][::-1], "depth decreases"),
    (P[:-5], uniform_table(2100, 2200)[1][:-5], "end at P0"),
    (P, -uniform_table(2100, 2200)[1], "positive down"),
    (np.array([100, 50, 50, 0.0]), np.array([1, 2, 3, 4.0]), "fall strictly"),
])
def test_validation(p, d, match):
    """T15: a reversed or malformed table is refused with the reason."""
    with pytest.raises(TableError, match=match):
        validate_table(p, d)


def test_headers_and_flip(project):
    for header in ("Value", "Depth(m)"):
        text = f"Percentile,{header}\n" + "\n".join(
            f"{p:g},{d:.3f}" for p, d in zip(*uniform_table(2100, 2200)))
        p, d, col = parse_csv(text.encode())
        assert col == header and d[0] == 2100
    negative = "Percentile,Value\n" + "\n".join(
        f"{p:g},{-d:.3f}" for p, d in zip(*uniform_table(2100, 2200)))
    with pytest.raises(OperationError, match="positive down"):
        import_hcwc(project, name="neg", basis="geological", conditioning="unconditioned",
                    tails="raw", csv=("neg.csv", negative.encode()))
    assert not project.sources                            # nothing kept from a refused import
    dist = import_hcwc(project, name="flipped", basis="geological", conditioning="unconditioned",
                       tails="raw", csv=("neg.csv", negative.encode()), flip_sign=True)
    assert dist.depths[0] == 2100 and "sign flipped" in dist.origin


def test_point_mass_is_a_step():
    """T16: 30 % of contacts at 2200 m: E just above 2200 is 0.30, at 2200 it is 0 (strict)."""
    d = np.where(P <= 30, 2200.0, 2200 - 100 * (P - 30) / 70)
    e = Exceedance(P, d)
    assert float(e(2199.99)) >= 0.30
    assert float(e(2200.0)) == 0.0
    assert float(e(2150.0)) == pytest.approx(0.30 + 0.70 * 0.5, abs=1e-9)


def test_truncated_tails_within_the_stated_bound():
    """T17: a normal distribution, tails truncated at P99.5/P0.5 as the Builder does."""
    mu, sigma = 2200.0, 40.0
    cumulative = np.clip(100 - P, 0.5, 99.5) / 100
    e = Exceedance(P, mu + sigma * norm.ppf(cumulative))
    z = np.linspace(2050, 2350, 601)
    assert np.max(np.abs(e(z) - norm.sf(z, mu, sigma))) <= 0.015


def test_builder_files():
    p, d, col = parse_csv((FIX / "hcwc_percentiles_geological.csv").read_bytes())
    validate_table(p, d)
    assert col == "Value" and p[0] == 100 and d[0] < d[-1]
    info = parse_hcwc_json((FIX / "example_prospect_spill.hcwc.json").read_bytes())
    assert info["p_g"] == pytest.approx(0.40824, abs=1e-9)
    assert info["h_min"] == 100.0                         # inputs, not the stale resolved 120
    assert info["apex"] == pytest.approx(2050.0)
    assert basis_from_filename("hcwc_percentiles_geological.csv") == "geological"
    assert basis_from_filename("hcwc_percentiles_Given_DHI.csv") == "given_dhi"
    assert basis_from_filename("contacts.csv") is None


def test_json_fills_blanks_and_typed_values_win(project):
    dist = import_hcwc(project, name="builder", basis="geological", conditioning="h_min",
                       tails="truncated",
                       csv=("hcwc_percentiles_geological.csv",
                            (FIX / "hcwc_percentiles_geological.csv").read_bytes()),
                       json=("example.hcwc.json",
                             (FIX / "example_prospect_spill.hcwc.json").read_bytes()),
                       h_min=120.0, f_hmin=0.8891)
    assert dist.p_g == pytest.approx(0.40824)
    assert dist.h_min == 120.0 and dist.apex == pytest.approx(2050.0)
    assert any("from example.hcwc.json inputs" in s for s in dist.sources)
    assert any(s.startswith("h_min = 120 typed") for s in dist.sources)
    assert len(project.sources) == 2


def test_prior_p_g_refused_for_a_dhi_table(project):
    """C2: a given-the-DHI table with the prior P(G) from the prospect file is refused."""
    with pytest.raises(OperationError, match="P\\(G \\| DHI\\)"):
        import_hcwc(project, name="dhi", basis="given_dhi", conditioning="h_min",
                    tails="truncated",
                    csv=("hcwc_percentiles_Given_DHI.csv",
                         (FIX / "hcwc_percentiles_geological.csv").read_bytes()),
                    json=("example.hcwc.json",
                          (FIX / "example_prospect_spill.hcwc.json").read_bytes()))


def test_pasted_table():
    text = "Percentile\tDepth\n" + "\n".join(f"{p:g}\t{d:.2f}"
                                              for p, d in zip(*uniform_table(2100, 2200)))
    p, d = parse_pasted(text)
    validate_table(p, d)
    with pytest.raises(TableError, match="line"):
        parse_pasted("100 2100\n50 x\n0 2200")



def test_builder_spill_is_compared(project):
    """C5: the spill typed in the Builder prospect against the confirmed map spill."""
    from tests.test_pos import dome

    top, closure = dome(project, crest=2050.0)                  # spills at the edge, 2275 m
    dist = import_hcwc(project, name="builder", basis="geological", conditioning="h_min",
                       tails="truncated", f_hmin=0.8891, h_min=120.0,
                       csv=("hcwc_percentiles_geological.csv",
                            (FIX / "hcwc_percentiles_geological.csv").read_bytes()),
                       json=("example.hcwc.json",
                             (FIX / "example_prospect_spill.hcwc.json").read_bytes()))
    assert dist.builder_spill == 2200.0
    from posgridder.core.operations import apply
    m = apply(project, "pos_map", [closure.uid, top.uid, dist.uid],
              {"roles": ["closure", "top", "hcwc"], "event": "a"}, name="m")
    assert any("differs from the spill in the Builder prospect" in w for w in m.warnings)
