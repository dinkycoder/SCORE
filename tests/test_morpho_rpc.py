"""
tests/test_morpho_rpc.py - MorphoRPCClient's own conversion/decode logic.

These tests cover what's actually new: Morpho's shares math and the
raw-data -> MarketPosition conversion. They also include ONE test that
runs extract_features() on a synthetic Morpho-sourced WalletPosition
(test_extract_features_on_morpho_position below) - added after a
whole-branch review found that no test anywhere exercised that path,
which is why the volatility_mismatch structural limitation documented in
src/morpho/rpc.py's module docstring went undetected through 5 individual
task reviews.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from morpho.rpc import shares_to_assets_up, build_market_position, is_empty_position
from base.rpc import WalletPosition
from scoring.features import extract_features


def test_shares_to_assets_up_rounds_up_not_down():
    """Hand-verified: 500_000_000 shares of a 1_000_000_000-share pool
    holding 999 total assets is 499.5009... Morpho rounds UP for a
    borrower's owed amount (SharesMathLib.toAssetsUp), so this must come
    out to 500, not 499 - a wallet's debt must never be understated by
    rounding."""
    assert shares_to_assets_up(500_000_000, 999, 1_000_000_000) == 500


def test_build_market_position_converts_raw_data_to_usd():
    """1.0 cbBTC collateral (8 decimals) at a price implying $100,000/BTC,
    against $50,000 (raw 6-decimal USDC) already-converted borrowed
    assets. Hand-verified: collateral_price_1e36 = 10**39 means
    1 cbBTC (1e8 raw) -> 1e8 * 1e39 // 1e36 = 1e11 raw USDC = $100,000."""
    position = build_market_position(
        market_id_hex="0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836",
        collateral_raw=100_000_000,       # 1.0 cbBTC
        borrowed_assets_raw=50_000_000_000,  # $50,000 in raw USDC
        collateral_price_1e36=10 ** 39,
        collateral_decimals=8,
        loan_decimals=6,
    )

    assert position.symbol == "cbBTC"
    assert position.supplied_underlying == pytest.approx(1.0)
    assert position.borrowed_underlying == pytest.approx(50_000.0)
    assert position.collateral_usd == pytest.approx(100_000.0)
    assert position.debt_usd == pytest.approx(50_000.0)
    assert position.collateral_factor == pytest.approx(0.86)
    assert position.is_entered is True


def test_build_market_position_with_no_debt():
    """A supplier with no borrow - debt_usd and borrowed_underlying must
    be exactly zero, not a rounding artifact."""
    position = build_market_position(
        market_id_hex="0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836",
        collateral_raw=100_000_000,
        borrowed_assets_raw=0,
        collateral_price_1e36=10 ** 39,
        collateral_decimals=8,
        loan_decimals=6,
    )
    assert position.debt_usd == 0.0
    assert position.borrowed_underlying == 0.0


def test_healthy_position_is_not_underwater():
    market = build_market_position(
        market_id_hex="0xtest",
        collateral_raw=100_000_000,          # 1.0 cbBTC
        borrowed_assets_raw=50_000_000_000,  # $50,000 - well under 86% LLTV
        collateral_price_1e36=10 ** 39,       # $100,000/BTC
        collateral_decimals=8,
        loan_decimals=6,
    )
    weighted = market.weighted_collateral_usd
    debt = market.debt_usd
    position = WalletPosition(
        wallet_address="0x" + "aa" * 20, block_number=1, markets=[market],
        reported_liquidity_usd=max(0.0, weighted - debt),
        reported_shortfall_usd=max(0.0, debt - weighted),
    )
    assert position.is_underwater is False


def test_underwater_position_is_flagged():
    """Debt exceeds weighted collateral (100,000 * 0.86 = 86,000 <
    95,000 borrowed) - must be flagged, not silently reported healthy the
    way the None-collateral-factor and not-entered-market bugs silently
    reported healthy in the Moonwell path."""
    market = build_market_position(
        market_id_hex="0xtest",
        collateral_raw=100_000_000,          # 1.0 cbBTC = $100,000 @ this price
        borrowed_assets_raw=95_000_000_000,  # $95,000 > 86,000 LLTV threshold
        collateral_price_1e36=10 ** 39,
        collateral_decimals=8,
        loan_decimals=6,
    )
    weighted = market.weighted_collateral_usd
    debt = market.debt_usd
    assert debt > weighted  # sanity check on the test's own premise
    position = WalletPosition(
        wallet_address="0x" + "aa" * 20, block_number=1, markets=[market],
        reported_liquidity_usd=max(0.0, weighted - debt),
        reported_shortfall_usd=max(0.0, debt - weighted),
    )
    assert position.is_underwater is True


def test_extract_features_on_morpho_position():
    """
    The ONE place extract_features() is actually exercised on a
    Morpho-sourced WalletPosition (see this file's module docstring for
    why this test exists: it closes a gap that let a real bug through 5
    individual task reviews).

    1.0 cbBTC ($100,000 @ this price) against $50,000 USDC debt -
    volatile-collateral/stable-debt, the textbook case
    `volatility_mismatch` exists to catch. It still comes out False here,
    intentionally documented as a known, permanent limitation (see
    src/morpho/rpc.py's module docstring): build_market_position packs
    collateral and debt into a single MarketPosition under one symbol
    ("cbBTC"), so extract_features()'s collateral-symbols-vs-debt-symbols
    comparison always sees the same one-element set on both sides.
    `market_count` is also asserted at its degenerate value of 1.
    """
    market = build_market_position(
        market_id_hex="0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836",
        collateral_raw=100_000_000,          # 1.0 cbBTC
        borrowed_assets_raw=50_000_000_000,  # $50,000 USDC
        collateral_price_1e36=10 ** 39,       # $100,000/BTC
        collateral_decimals=8,
        loan_decimals=6,
    )
    weighted = market.weighted_collateral_usd  # 100,000 * 0.86 = 86,000
    debt = market.debt_usd                     # 50,000

    position = WalletPosition(
        wallet_address="0x" + "cc" * 20,
        block_number=12345,
        markets=[market],
        reported_liquidity_usd=max(0.0, weighted - debt),
        reported_shortfall_usd=max(0.0, debt - weighted),
    )

    features = extract_features(position)

    assert features.ltv == pytest.approx(0.5, abs=1e-6)
    assert features.capacity_used == pytest.approx(0.581395, abs=1e-6)
    assert features.headroom == pytest.approx(0.418605, abs=1e-6)
    assert features.degraded is False
    assert features.collateral_usd == pytest.approx(100_000.0)
    assert features.debt_usd == pytest.approx(50_000.0)
    assert features.exposure_usd == pytest.approx(50_000.0)
    assert features.market_count == 1  # degenerate for Morpho - see docstring
    assert features.volatility_mismatch is False  # known limitation - see docstring
    assert features.debt_rise_to_liquidation == pytest.approx(0.72, abs=1e-6)
    assert features.is_underwater is False
    assert features.is_borrower is True


def test_is_empty_position_true_for_zero_collateral_and_zero_borrow():
    """A wallet with no collateral and no borrow shares on this market has
    no position at all. get_wallet_position uses this to return
    markets=[] (market_count=0) instead of a phantom one-element list of
    all-zero values - mirroring BaseRPCClient.get_wallet_position's
    `if m_bal == 0 and borrow_bal == 0: continue` skip. Exercised directly
    since a live zero-position wallet isn't a stable thing to depend on
    in a test."""
    assert is_empty_position(collateral_raw=0, borrow_shares=0) is True


def test_is_empty_position_false_when_only_collateral_present():
    """A supplier with collateral but no borrow still has a real position
    (it's usable collateral, just unborrowed against) - must not be
    treated as empty."""
    assert is_empty_position(collateral_raw=100_000_000, borrow_shares=0) is False


def test_is_empty_position_false_when_only_borrow_shares_present():
    """Borrow shares outstanding with zero collateral is itself a real
    (if unusual/underwater) position - must not be treated as empty."""
    assert is_empty_position(collateral_raw=0, borrow_shares=1) is False


@pytest.mark.live
def test_get_wallet_position_reads_a_real_open_position():
    """A real wallet with a confirmed open position on the cbBTC/USDC
    market as of 2026-08-23 (found via Borrow-event scan, position()
    confirmed non-zero at the time - see
    docs/superpowers/specs/2026-08-23-morpho-reader-design.md for the
    method; if this wallet has since closed out, use the same
    Borrow-event-scan technique to find a replacement, the way
    tests/test_latency.py's TEST_WALLET was replaced)."""
    from morpho.rpc import MorphoRPCClient

    client = MorphoRPCClient()
    position = client.get_wallet_position("0x04a9530da51Eb174153F150FfDF103B368c332E5")

    assert len(position.markets) == 1
    market = position.markets[0]
    assert market.symbol == "cbBTC"
    assert market.supplied_underlying > 0
    assert market.debt_usd > 0
    # Sanity bound, not an exact figure - cbBTC/BTC has traded well
    # within this band across 2025-2026; catches a decimals/scaling bug
    # that would produce an implausible price, without hardcoding
    # today's exact BTC price into a test that will go stale.
    implied_btc_price = market.collateral_usd / market.supplied_underlying
    assert 10_000 < implied_btc_price < 500_000
