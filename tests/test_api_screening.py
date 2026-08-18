"""
tests/test_api_screening.py - the /position endpoint must fail CLOSED when
sanctions screening cannot be verified, and must surface a match when it can.

The RPC client and screener are replaced with test doubles so this runs
without network or chain access. What is under test is the ENDPOINT's
control flow around screening, not the screener internals (covered in
test_sanctions.py) or the RPC client.
"""

import sys
from pathlib import Path
from dataclasses import dataclass

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import api.server as server
from compliance.sanctions import StaleListError, ListUnavailableError


CLEAN = "0xAA503ae37ba4A6FCC2fD6CC3F3Dc776Ab11B7b67"


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c
    # reset module singletons between tests
    server._client = None
    server._screener = None


# -- test doubles ---------------------------------------------------------

@dataclass
class FakeScreeningResult:
    address: str
    is_sanctioned: bool
    list_age_hours: float = 1.0
    list_source: str = "test"
    def __bool__(self): return self.is_sanctioned


class CleanScreener:
    def screen(self, addr): return FakeScreeningResult(addr, False)


class SanctionedScreener:
    def screen(self, addr): return FakeScreeningResult(addr, True)


class StaleScreener:
    def screen(self, addr): raise StaleListError("stale in test")


class AbsentScreener:
    def screen(self, addr): raise ListUnavailableError("absent in test")


@dataclass
class FakeMarket:
    symbol: str = "mUSDC"
    supplied_underlying: float = 100.0
    borrowed_underlying: float = 0.0
    collateral_usd: float = 100.0
    debt_usd: float = 0.0
    collateral_factor: float = 0.85


class FakePosition:
    wallet_address = CLEAN
    block_number = 50_000_000
    markets = [FakeMarket()]
    reported_liquidity_usd = 85.0
    reported_shortfall_usd = 0.0
    total_collateral_usd = 100.0
    total_weighted_collateral_usd = 85.0
    total_debt_usd = 0.0
    is_underwater = False
    market_count = 1


class FakeClient:
    def get_wallet_position(self, addr): return FakePosition()


# -- the tests ------------------------------------------------------------

def test_stale_list_fails_closed(client, monkeypatch):
    """A stale sanctions list must yield 503, not a position."""
    server._screener = StaleScreener()
    server._client = FakeClient()
    resp = client.get("/position/" + CLEAN)
    assert resp.status_code == 503
    assert "screening unavailable" in resp.get_json()["error"].lower()


def test_absent_list_fails_closed(client, monkeypatch):
    """No sanctions list at all must yield 503, not a position."""
    server._screener = AbsentScreener()
    server._client = FakeClient()
    resp = client.get("/position/" + CLEAN)
    assert resp.status_code == 503


def test_clean_address_returns_position(client, monkeypatch):
    """A clean, verified address returns a position with is_sanctioned False."""
    server._screener = CleanScreener()
    server._client = FakeClient()
    resp = client.get("/position/" + CLEAN)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sanctions"]["is_sanctioned"] is False
    assert "features" in body


def test_sanctioned_address_is_flagged_not_hidden(client, monkeypatch):
    """A sanctioned address still returns a position, but flagged."""
    server._screener = SanctionedScreener()
    server._client = FakeClient()
    resp = client.get("/position/" + CLEAN)
    assert resp.status_code == 200
    assert resp.get_json()["sanctions"]["is_sanctioned"] is True


def test_invalid_address_rejected_before_screening(client):
    """A malformed address is a 400 and never reaches screening."""
    resp = client.get("/position/not-an-address")
    assert resp.status_code == 400
