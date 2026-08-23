"""
src/morpho/rpc.py - Read wallet positions from one Morpho Blue market on
Base (cbBTC/USDC). See docs/superpowers/specs/2026-08-23-morpho-reader-design.md
for why this market, why single-market scope, and why
reported_liquidity_usd/reported_shortfall_usd here are NOT the same kind
of independent protocol check Moonwell's getAccountLiquidity provides.
"""

from typing import List, Optional, Tuple

from eth_abi import decode as abi_decode
from web3 import Web3

from base.rpc import MarketPosition, MULTICALL3, MULTICALL3_ABI, WalletPosition
from base import config as base_config

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


MORPHO_ABI = [
    {"inputs": [{"name": "id", "type": "bytes32"}, {"name": "user", "type": "address"}],
     "name": "position",
     "outputs": [
         {"name": "supplyShares", "type": "uint256"},
         {"name": "borrowShares", "type": "uint128"},
         {"name": "collateral", "type": "uint128"},
     ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "id", "type": "bytes32"}], "name": "market",
     "outputs": [
         {"name": "totalSupplyAssets", "type": "uint128"},
         {"name": "totalSupplyShares", "type": "uint128"},
         {"name": "totalBorrowAssets", "type": "uint128"},
         {"name": "totalBorrowShares", "type": "uint128"},
         {"name": "lastUpdate", "type": "uint128"},
         {"name": "fee", "type": "uint128"},
     ], "stateMutability": "view", "type": "function"},
]

ORACLE_ABI = [
    {"inputs": [], "name": "price", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]


class MorphoRPCClient:
    """
    Reads one wallet's position on the Morpho Blue cbBTC/USDC market on
    Base (config.MARKET_ID). Single-market scope - see
    docs/superpowers/specs/2026-08-23-morpho-reader-design.md.
    """

    def __init__(self, rpc_url: Optional[str] = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or base_config.RPC_URL))
        chain_id = self.w3.eth.chain_id
        if chain_id != base_config.CHAIN_ID:
            raise ValueError(
                "Connected to chain " + str(chain_id) + ", expected "
                + str(base_config.CHAIN_ID) + " (Base mainnet)."
            )

        self.multicall = self.w3.eth.contract(
            address=Web3.to_checksum_address(MULTICALL3), abi=MULTICALL3_ABI)
        self.morpho = self.w3.eth.contract(
            address=Web3.to_checksum_address(config.MORPHO_BLUE_ADDRESS),
            abi=MORPHO_ABI)
        self.oracle = self.w3.eth.contract(
            address=Web3.to_checksum_address(config.ORACLE), abi=ORACLE_ABI)

    @staticmethod
    def _encode(contract, fn_name: str, args: Optional[list] = None) -> str:
        args = args or []
        try:
            return contract.encode_abi(fn_name, args)
        except (AttributeError, TypeError):
            return contract.encodeABI(fn_name=fn_name, args=args)

    def get_wallet_position(self, wallet: str) -> WalletPosition:
        """Full position on the cbBTC/USDC market, in ONE round trip."""
        addr = Web3.to_checksum_address(wallet)
        market_id = config.MARKET_ID

        calls: List[Tuple[str, bool, str]] = [
            (Web3.to_checksum_address(MULTICALL3), False,
             self._encode(self.multicall, "getBlockNumber")),
            (config.MORPHO_BLUE_ADDRESS, False,
             self._encode(self.morpho, "position", [market_id, addr])),
            (config.MORPHO_BLUE_ADDRESS, False,
             self._encode(self.morpho, "market", [market_id])),
            (config.ORACLE, False,
             self._encode(self.oracle, "price")),
        ]
        results = self.multicall.functions.aggregate3(calls).call()

        block_number = abi_decode(["uint256"], results[0][1])[0]
        _supply_shares, borrow_shares, collateral_raw = abi_decode(
            ["uint256", "uint128", "uint128"], results[1][1])
        (_total_supply_assets, _total_supply_shares,
         total_borrow_assets, total_borrow_shares,
         _last_update, _fee) = abi_decode(
            ["uint128"] * 6, results[2][1])
        price_1e36 = abi_decode(["uint256"], results[3][1])[0]

        borrowed_assets_raw = shares_to_assets_up(
            borrow_shares, total_borrow_assets, total_borrow_shares)

        market_position = build_market_position(
            market_id_hex=market_id,
            collateral_raw=collateral_raw,
            borrowed_assets_raw=borrowed_assets_raw,
            collateral_price_1e36=price_1e36,
            collateral_decimals=config.COLLATERAL_DECIMALS,
            loan_decimals=config.LOAN_DECIMALS,
        )

        weighted = market_position.weighted_collateral_usd
        debt = market_position.debt_usd

        return WalletPosition(
            wallet_address=addr,
            block_number=block_number,
            markets=[market_position],
            # NOT an independent protocol-side check, unlike Moonwell's
            # getAccountLiquidity - Morpho Blue exposes no such call (see
            # design spec §6). This is our own math, duplicated here only
            # so WalletPosition.is_underwater works correctly instead of
            # silently defaulting to False.
            reported_liquidity_usd=max(0.0, weighted - debt),
            reported_shortfall_usd=max(0.0, debt - weighted),
        )
