"""
tests/test_api_endpoints.py - /health, /capabilities, and the 404 handler.

/position's control flow (sanctions fail-closed behaviour) is covered
separately in test_api_screening.py. These two endpoints take no wallet
argument and touch no RPC client or screener, so they're tested directly
against the real app with no test doubles needed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import api.server as server
import base.config as config


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


# -- /health ----------------------------------------------------------------

def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "SCORE"


def test_health_reports_the_real_chain_id(client):
    """Regression guard: this must be Base mainnet (8453), not whatever a
    future multi-chain change might default to."""
    resp = client.get("/health")
    assert resp.get_json()["chain_id"] == config.CHAIN_ID == 8453


# -- /capabilities ------------------------------------------------------------

def test_capabilities_returns_ok(client):
    resp = client.get("/capabilities")
    assert resp.status_code == 200


def test_capabilities_implemented_matches_actual_feature_set(client):
    """Regression guard for the exact defect this project keeps
    re-encountering: a doc/API claim drifting from what the code actually
    computes. Every field CreditFeatures.to_dict() produces must be
    listed as implemented, and nothing listed that it doesn't produce -
    both directions of drift are checked, not just additions."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from base.rpc import WalletPosition
    from scoring.features import extract_features

    real_feature_keys = set(extract_features(WalletPosition(
        wallet_address="0x" + "aa" * 20, block_number=1,
    )).to_dict().keys())

    body = client.get("/capabilities").get_json()
    listed = set(body["implemented"]["point_in_time_solvency"])

    assert listed == real_feature_keys


def test_capabilities_not_implemented_items_have_reasons(client):
    """Every not-yet-built capability must say WHY, not just that it's
    missing - an empty or missing reason is the kind of claim this
    endpoint exists specifically to prevent."""
    body = client.get("/capabilities").get_json()
    not_implemented = body["not_implemented"]
    assert len(not_implemented) > 0
    for name, reason in not_implemented.items():
        assert isinstance(reason, str) and len(reason) > 10, (
            name + " has no real explanation")


def test_capabilities_reports_protocol_and_network(client):
    body = client.get("/capabilities").get_json()
    assert body["protocol"] == "Moonwell"
    assert body["network"] == "Base mainnet"


def test_capabilities_lists_ofac_screening_as_compliance_not_solvency(client):
    """Sanctions screening is a compliance control, not a credit feature -
    the two must not be conflated under one list."""
    body = client.get("/capabilities").get_json()
    assert "ofac_sdn_screening" in body["implemented"]["compliance"]
    assert "ofac_sdn_screening" not in body["implemented"]["point_in_time_solvency"]


# -- unknown routes -----------------------------------------------------------

def test_unknown_route_returns_404(client):
    resp = client.get("/not-a-real-route")
    assert resp.status_code == 404
    assert "error" in resp.get_json()
