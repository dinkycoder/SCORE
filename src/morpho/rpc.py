"""
src/morpho/rpc.py - Read wallet positions from one Morpho Blue market on
Base (cbBTC/USDC). See docs/superpowers/specs/2026-08-23-morpho-reader-design.md
for why this market, why single-market scope, and why
reported_liquidity_usd/reported_shortfall_usd here are NOT the same kind
of independent protocol check Moonwell's getAccountLiquidity provides.
"""

from base.rpc import MarketPosition

from . import config

VIRTUAL_SHARES = 10 ** 6
VIRTUAL_ASSETS = 1


def shares_to_assets_up(shares: int, total_assets: int, total_shares: int) -> int:
    """
    Morpho Blue's toAssetsUp (SharesMathLib): converts a shares balance to
    the underlying asset amount it represents, rounded UP - the same
    direction Morpho itself uses for a borrower's owed amount, so a
    wallet's debt is never understated by rounding. The
    +VIRTUAL_ASSETS/+VIRTUAL_SHARES offsets match Morpho Blue's own
    formula exactly (an anti-inflation-attack measure active from
    genesis, not an approximation).
    """
    numerator = shares * (total_assets + VIRTUAL_ASSETS)
    denominator = total_shares + VIRTUAL_SHARES
    return -(-numerator // denominator)  # ceiling division, exact integers


def build_market_position(
    market_id_hex: str,
    collateral_raw: int,
    borrowed_assets_raw: int,
    collateral_price_1e36: int,
    collateral_decimals: int,
    loan_decimals: int,
) -> MarketPosition:
    """
    Builds the existing MarketPosition dataclass from raw Morpho Blue
    market data, so extract_features() can consume a Morpho position
    without any changes.

    `borrowed_assets_raw` is ALREADY in asset units (apply
    shares_to_assets_up to a raw borrowShares value before calling this -
    kept as a separate step so this function's own arithmetic, tested
    here, doesn't also have to re-verify the shares conversion).

    collateral_price_1e36 follows Morpho's IOracle convention: the price
    of 1 whole collateral-token unit quoted in 1 whole loan-token unit,
    scaled by 1e36 - confirmed empirically 2026-08-23 (see Task 3):
    collateral_raw * price // 10**36 gives loan-token RAW units directly,
    with no further per-decimals adjustment needed.
    """
    collateral_value_in_loan_raw = (
        collateral_raw * collateral_price_1e36 // 10 ** 36
    )

    # USDC (the loan token here) is treated as ~$1 - a documented
    # simplification specific to this market's loan token being a
    # stablecoin, not a general assumption that would hold for any
    # Morpho market (see design spec §3 footnote).
    collateral_usd = collateral_value_in_loan_raw / (10 ** loan_decimals)
    debt_usd = borrowed_assets_raw / (10 ** loan_decimals)

    return MarketPosition(
        market_address=market_id_hex,
        symbol=config.COLLATERAL_SYMBOL,
        supplied_underlying=collateral_raw / (10 ** collateral_decimals),
        borrowed_underlying=borrowed_assets_raw / (10 ** loan_decimals),
        collateral_usd=collateral_usd,
        debt_usd=debt_usd,
        collateral_factor=config.LLTV,
        is_entered=True,  # Morpho Blue has no separate "enter market" step
    )
