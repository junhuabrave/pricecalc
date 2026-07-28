from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from pricecalc.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


ATM_CALL = {
    "spot": 100.0,
    "strike": 100.0,
    "rate": 0.05,
    "div_yield": 0.0,
    "vol": 0.20,
    "tau_years": 1.0,
    "option_type": "call",
}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


class TestEvaluate:
    def test_returns_textbook_price_and_greeks(self, client):
        r = client.post("/api/pricing/evaluate", json=ATM_CALL)
        assert r.status_code == 200
        body = r.json()
        assert body["price"] == pytest.approx(10.450583572185565, rel=1e-9)
        assert body["greeks"]["delta"] == pytest.approx(0.6368306511756191, rel=1e-9)
        assert body["forward"] == pytest.approx(100.0 * math.exp(0.05), rel=1e-9)
        assert body["time_value"] == pytest.approx(body["price"], rel=1e-9)

    def test_rejects_negative_spot(self, client):
        r = client.post("/api/pricing/evaluate", json={**ATM_CALL, "spot": -1.0})
        assert r.status_code == 422

    def test_rejects_unknown_option_type(self, client):
        r = client.post("/api/pricing/evaluate", json={**ATM_CALL, "option_type": "swaption"})
        assert r.status_code == 422


class TestImpliedVol:
    def test_round_trips_a_priced_option(self, client):
        priced = client.post("/api/pricing/evaluate", json=ATM_CALL).json()
        payload = {k: v for k, v in ATM_CALL.items() if k != "vol"}
        r = client.post("/api/pricing/implied-vol", json={**payload, "price": priced["price"]})
        assert r.status_code == 200
        assert r.json()["implied_vol"] == pytest.approx(0.20, rel=1e-6)

    def test_price_above_upper_bound_returns_422_with_the_band(self, client):
        payload = {k: v for k, v in ATM_CALL.items() if k != "vol"}
        r = client.post("/api/pricing/implied-vol", json={**payload, "price": 500.0})
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert "upper bound" in detail["message"]
        assert detail["upper_bound"] == pytest.approx(100.0)


class TestSweep:
    def test_defaults_to_a_band_around_spot(self, client):
        r = client.post("/api/pricing/sweep", json={**ATM_CALL, "steps": 51})
        assert r.status_code == 200
        pts = r.json()["points"]
        assert len(pts) == 51
        assert pts[0]["spot"] == pytest.approx(60.0)
        assert pts[-1]["spot"] == pytest.approx(140.0)

    def test_delta_is_monotonic_in_spot_for_a_call(self, client):
        """Positive gamma means the call delta rises with spot, everywhere."""
        pts = client.post("/api/pricing/sweep", json={**ATM_CALL, "steps": 41}).json()["points"]
        deltas = [p["delta"] for p in pts]
        assert all(b >= a for a, b in zip(deltas[:-1], deltas[1:], strict=True))
        assert deltas[0] < 0.05 and deltas[-1] > 0.95

    def test_price_dominates_intrinsic(self, client):
        pts = client.post("/api/pricing/sweep", json={**ATM_CALL, "steps": 41}).json()["points"]
        assert all(p["price"] >= p["intrinsic"] - 1e-9 for p in pts)

    def test_rejects_inverted_range(self, client):
        r = client.post(
            "/api/pricing/sweep", json={**ATM_CALL, "spot_min": 120.0, "spot_max": 80.0}
        )
        assert r.status_code == 422
