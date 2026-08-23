"""
src/morpho/rpc.py - Read wallet positions from one Morpho Blue market on
Base (cbBTC/USDC). See docs/superpowers/specs/2026-08-23-morpho-reader-design.md
for why this market, why single-market scope, and why
reported_liquidity_usd/reported_shortfall_usd here are NOT the same kind
of independent protocol check Moonwell's getAccountLiquidity provides.
"""

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
