from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pricecalc.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


BASE = {"spot": 100.0, "rate": 0.0, "div_yield": 0.0}


def opt(kind, qty, strike, entry, tau=0.25, vol=0.2):
    return {
        "kind": kind,
        "quantity": qty,
        "entry_price": entry,
        "strike": strike,
        "tau": tau,
        "vol": vol,
    }


class TestPresetCatalogue:
    def test_lists_every_preset_with_a_summary(self, client):
        body = client.get("/api/strategy/presets").json()
        assert len(body) >= 10
        assert all(p["summary"] for p in body)
        assert {"long_call", "straddle", "iron_condor"} <= {p["id"] for p in body}


class TestAnalyse:
    def test_long_call_reports_unbounded_upside(self, client):
        r = client.post(
            "/api/strategy/analyse",
            json={**BASE, "legs": [opt("call", 1.0, 100.0, 4.0)]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["max_profit"]["unbounded"] is True
        # JSON has no infinity, so an unbounded extreme is sent as null.
        assert body["max_profit"]["value"] is None
        assert body["max_loss"]["value"] == pytest.approx(-4.0)
        assert body["breakevens"] == pytest.approx([104.0])

    def test_bull_call_spread_is_capped_both_ways(self, client):
        body = client.post(
            "/api/strategy/analyse",
            json={
                **BASE,
                "legs": [opt("call", 1.0, 100.0, 6.0), opt("call", -1.0, 110.0, 2.0)],
            },
        ).json()
        assert body["max_profit"]["value"] == pytest.approx(6.0)
        assert body["max_loss"]["value"] == pytest.approx(-4.0)
        assert body["net_cost"] == pytest.approx(4.0)
        assert body["payoff_slope_up"] == pytest.approx(0.0)

    def test_curve_includes_every_kink(self, client):
        body = client.post(
            "/api/strategy/analyse",
            json={
                **BASE,
                "legs": [opt("call", 1.0, 97.3, 6.0), opt("call", -1.0, 113.7, 2.0)],
                "steps": 21,
            },
        ).json()
        spots = [p["spot"] for p in body["curve"]]
        assert any(s == pytest.approx(97.3) for s in spots)
        assert any(s == pytest.approx(113.7) for s in spots)
        assert body["kinks"] == pytest.approx([97.3, 113.7])

    def test_underlying_leg_needs_no_contract_terms(self, client):
        r = client.post(
            "/api/strategy/analyse",
            json={
                **BASE,
                "legs": [{"kind": "underlying", "quantity": 1.0, "entry_price": 100.0}],
            },
        )
        assert r.status_code == 200
        assert r.json()["net_greeks"]["delta"] == pytest.approx(1.0)

    def test_rejects_an_option_leg_missing_its_terms(self, client):
        r = client.post(
            "/api/strategy/analyse",
            json={**BASE, "legs": [{"kind": "call", "quantity": 1.0, "entry_price": 4.0}]},
        )
        assert r.status_code == 422

    def test_rejects_a_zero_quantity_leg(self, client):
        r = client.post(
            "/api/strategy/analyse",
            json={**BASE, "legs": [opt("call", 0.0, 100.0, 4.0)]},
        )
        assert r.status_code == 422

    def test_rejects_an_empty_strategy(self, client):
        r = client.post("/api/strategy/analyse", json={**BASE, "legs": []})
        assert r.status_code == 422


class TestPresetEndpoint:
    @pytest.mark.parametrize(
        "preset",
        [
            "long_call",
            "long_put",
            "bull_call_spread",
            "bear_put_spread",
            "straddle",
            "strangle",
            "butterfly",
            "iron_condor",
            "covered_call",
            "collar",
            "calendar",
        ],
    )
    def test_every_preset_builds_and_analyses(self, client, preset):
        r = client.post("/api/strategy/preset", json={"preset": preset, **BASE})
        assert r.status_code == 200
        body = r.json()
        assert body["legs"]
        assert body["preset"] == preset
        assert body["summary"]
        assert body["curve"]

    def test_iron_condor_is_a_credit_with_capped_wings(self, client):
        body = client.post("/api/strategy/preset", json={"preset": "iron_condor", **BASE}).json()
        assert body["net_cost"] < 0
        assert body["max_profit"]["unbounded"] is False
        assert body["max_loss"]["unbounded"] is False
        assert len(body["legs"]) == 4

    def test_straddle_is_long_gamma_and_vega(self, client):
        body = client.post("/api/strategy/preset", json={"preset": "straddle", **BASE}).json()
        g = body["net_greeks"]
        assert g["gamma"] > 0 and g["vega"] > 0 and g["theta"] < 0

    def test_butterfly_is_short_gamma(self, client):
        body = client.post("/api/strategy/preset", json={"preset": "butterfly", **BASE}).json()
        g = body["net_greeks"]
        assert g["gamma"] < 0 and g["theta"] > 0

    def test_preset_legs_open_at_fair_value(self, client):
        """A preset carries no edge, so its net cost is pure theoretical value."""
        body = client.post("/api/strategy/preset", json={"preset": "butterfly", **BASE}).json()
        for leg in body["legs"]:
            if leg["kind"] == "underlying":
                continue
            priced = client.post(
                "/api/pricing/evaluate",
                json={
                    "spot": 100.0,
                    "strike": leg["strike"],
                    "rate": 0.0,
                    "div_yield": 0.0,
                    "vol": leg["vol"],
                    "tau_years": leg["tau"],
                    "option_type": leg["kind"],
                },
            ).json()
            assert leg["entry_price"] == pytest.approx(priced["price"], rel=1e-9)

    def test_rejects_an_unknown_preset(self, client):
        r = client.post("/api/strategy/preset", json={"preset": "moon_shot", **BASE})
        assert r.status_code == 422
