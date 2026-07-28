from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pricecalc.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


CLEAN = {"spot": 100.0, "rate": 0.04, "div_yield": 0.0, "n_violations": 0, "seed": 42}


class TestScan:
    def test_clean_chain_reports_nothing(self, client):
        """The contract the whole tab rests on: no mispricing, no findings."""
        body = client.post("/api/arbitrage/scan", json=CLEAN).json()
        assert body["violations"] == []
        assert body["summary"]["violations_found"] == 0
        assert body["summary"]["total_edge"] == 0.0
        assert body["summary"]["quotes_scanned"] > 0

    def test_planted_violations_are_reported(self, client):
        body = client.post("/api/arbitrage/scan", json={**CLEAN, "n_violations": 3}).json()
        assert body["summary"]["violations_found"] > 0
        assert body["summary"]["total_edge"] > 0
        assert len(body["planted"]) == 3

    def test_every_finding_carries_a_financed_trade(self, client):
        """Reported profit must equal the net cash flow of the published legs."""
        body = client.post("/api/arbitrage/scan", json={**CLEAN, "n_violations": 4}).json()
        assert body["violations"]
        for v in body["violations"]:
            assert v["legs"], v["summary"]
            net = sum(leg["cash_flow"] for leg in v["legs"])
            assert net == pytest.approx(v["profit"], abs=1e-9), v["summary"]

    def test_results_are_ranked_by_edge(self, client):
        body = client.post("/api/arbitrage/scan", json={**CLEAN, "n_violations": 4}).json()
        profits = [v["profit"] for v in body["violations"]]
        assert profits == sorted(profits, reverse=True)

    def test_min_edge_filters_findings(self, client):
        loose = client.post(
            "/api/arbitrage/scan", json={**CLEAN, "n_violations": 4, "min_edge": 0.001}
        ).json()
        strict = client.post(
            "/api/arbitrage/scan", json={**CLEAN, "n_violations": 4, "min_edge": 5.0}
        ).json()
        assert len(strict["violations"]) <= len(loose["violations"])
        assert all(v["profit"] > 5.0 for v in strict["violations"])

    def test_dividends_flag_calendar_checks_as_skipped(self, client):
        body = client.post("/api/arbitrage/scan", json={**CLEAN, "div_yield": 0.03}).json()
        assert body["summary"]["calendar_checks_skipped"] is True
        assert not any(v["kind"] == "calendar_monotonicity" for v in body["violations"])

    def test_scan_is_reproducible_from_the_request_alone(self, client):
        args = {**CLEAN, "n_violations": 3, "seed": 777}
        first = client.post("/api/arbitrage/scan", json=args).json()
        second = client.post("/api/arbitrage/scan", json=args).json()
        assert first == second

    def test_a_different_seed_moves_the_violations(self, client):
        a = client.post("/api/arbitrage/scan", json={**CLEAN, "n_violations": 3, "seed": 1}).json()
        b = client.post("/api/arbitrage/scan", json={**CLEAN, "n_violations": 3, "seed": 2}).json()
        assert a["planted"] != b["planted"]

    def test_chain_quotes_are_never_crossed(self, client):
        body = client.post("/api/arbitrage/scan", json={**CLEAN, "n_violations": 4}).json()
        for q in body["chain"]["quotes"]:
            assert q["ask"] >= q["bid"] >= 0.0

    def test_rejects_an_absurd_strike_ladder(self, client):
        r = client.post("/api/arbitrage/scan", json={**CLEAN, "strike_count": 999})
        assert r.status_code == 422
