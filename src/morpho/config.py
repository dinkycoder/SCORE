"""
src/morpho/config.py - Verified constants for the Morpho Blue cbBTC/USDC
market on Base. See docs/superpowers/specs/2026-08-23-morpho-reader-design.md
§3 for how these were confirmed (queried directly via idToMarketParams,
not taken from a webpage).

Only MARKET_ID and LLTV are permanent - LLTV is immutable per market
(it's literally part of what the market ID is derived from). Nothing
here is a TVL/volume figure; those change constantly and are not
recorded as constants.
"""

# Deterministic across chains only in the sense that Morpho deployed the
# same bytecode; the ADDRESS itself is Base-specific (unlike Multicall3's
# CREATE2 address). Confirmed via docs.morpho.org/get-started/resources/addresses/
# and eth_getCode (15,623 bytes) on 2026-08-23.
MORPHO_BLUE_ADDRESS = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"

# cbBTC/USDC on Base. Confirmed via idToMarketParams on 2026-08-23 - see
# the design spec for why this market (highest TVL of 3 candidates
# checked, volatile-collateral/stable-debt like Moonwell's dominant
# pattern).
MARKET_ID = "0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836"
LOAN_TOKEN = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"       # USDC
COLLATERAL_TOKEN = "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"  # cbBTC
ORACLE = "0x663BECd10daE6C4A3Dcd89F1d76c1174199639B9"
IRM = "0x46415998764C29aB2a25CbeA6254146D50D22687"              # Adaptive Curve IRM

LLTV_WAD = 860_000_000_000_000_000  # 0.86 * 1e18, confirmed via idToMarketParams
LLTV = 0.86

COLLATERAL_SYMBOL = "cbBTC"
COLLATERAL_DECIMALS = 8
LOAN_SYMBOL = "USDC"
LOAN_DECIMALS = 6
