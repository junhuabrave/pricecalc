from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pricecalc.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


BASE = {"spot": 100.0, "strike": 100.0, "expiry": 0.25, "steps": 200, "seed": 42}


class TestSimulate:
    def test_runs_a_session_and_attributes_pnl(self, client):
        r = client.post("/api/marketmaking/simulate", json=BASE)
        assert r.status_code == 200
        body = r.json()
        a = body["attribution"]
        assert a["spread_pnl"] + a["inventory_pnl"] + a["hedge_pnl"] == pytest.approx(
            a["total_pnl"]
        )
        assert len(body["steps"]) == 200

    def test_the_default_configuration_trades(self, client):
        """A simulation that never fills is broken, not conservative."""
        body = client.post("/api/marketmaking/simulate", json=BASE).json()
        assert body["fills"] > 0
        assert body["capture_per_fill"] > 0

    def test_spread_capture_is_never_negative(self, client):
        body = client.post("/api/marketmaking/simulate", json=BASE).json()
        assert body["attribution"]["spread_pnl"] >= 0

    def test_the_same_request_replays_the_same_session(self, client):
        first = client.post("/api/marketmaking/simulate", json=BASE).json()
        second = client.post("/api/marketmaking/simulate", json=BASE).json()
        assert first == second

    def test_a_risk_neutral_maker_never_skews(self, client):
        body = client.post("/api/marketmaking/simulate", json={**BASE, "risk_aversion": 0.0}).json()
        assert all(s["skew"] == 0.0 for s in body["steps"])

    def test_an_inventory_aware_maker_does_skew(self, client):
        body = client.post("/api/marketmaking/simulate", json={**BASE, "risk_aversion": 0.8}).json()
        assert any(s["skew"] != 0.0 for s in body["steps"])

    def test_skew_leans_against_inventory(self, client):
        """Skew opposes the position: long marks quotes down, short marks up.

        Asserted as a sign relationship rather than a strict inequality,
        because skew is proportional to the option's price variance and is
        legitimately zero when delta is zero — no first-order risk, nothing to
        lean against. Signed zero also makes strict comparison unreliable.
        """
        body = client.post("/api/marketmaking/simulate", json={**BASE, "risk_aversion": 0.8}).json()
        for s in body["steps"]:
            assert s["inventory"] * s["skew"] <= 0.0

        assert any(abs(s["skew"]) > 0.0 for s in body["steps"]), "skew never engaged"

    def test_disabling_the_hedge_removes_its_pnl(self, client):
        body = client.post("/api/marketmaking/simulate", json={**BASE, "hedge_delta": False}).json()
        assert body["attribution"]["hedge_pnl"] == pytest.approx(0.0)
        assert body["hedge_trades"] == 0

    def test_rejects_a_session_outliving_the_option(self, client):
        r = client.post("/api/marketmaking/simulate", json={**BASE, "horizon": 0.5})
        assert r.status_code == 422


class TestSweep:
    def test_covers_a_range_of_risk_aversion(self, client):
        body = client.post("/api/marketmaking/sweep?paths=4", json={**BASE, "steps": 120}).json()
        levels = [p["risk_aversion"] for p in body["points"]]
        assert levels == sorted(levels)
        assert 0.0 in levels
        assert body["paths_per_point"] == 4

    def test_caution_reduces_the_inventory_carried(self, client):
        """The claim the whole model rests on, measured across paths."""
        body = client.post("/api/marketmaking/sweep?paths=8", json={**BASE, "steps": 200}).json()
        points = body["points"]
        naive = next(p for p in points if p["risk_aversion"] == 0.0)
        cautious = max(points, key=lambda p: p["risk_aversion"])
        assert cautious["max_abs_inventory"] < naive["max_abs_inventory"]

    def test_wider_quotes_win_fewer_fills(self, client):
        body = client.post("/api/marketmaking/sweep?paths=8", json={**BASE, "steps": 200}).json()
        points = body["points"]
        naive = next(p for p in points if p["risk_aversion"] == 0.0)
        cautious = max(points, key=lambda p: p["risk_aversion"])
        assert cautious["fills"] < naive["fills"]
