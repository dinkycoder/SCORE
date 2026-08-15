"""
src/base/rpc.py - Read wallet positions from Moonwell on Base.

All calls are reads (eth_call): no transaction, no gas, no signature.

Scaling, which is the only subtle part:

    Let d = the underlying token's decimals (USDC 6, WETH 18, cbBTC 8).

    getAccountSnapshot -> (error, mTokenBalance, borrowBalance, exchangeRate)
        mTokenBalance   scaled 1e8
        borrowBalance   scaled 1e(d)
        exchangeRate    scaled 1e(18 - 8 + d)

    oracle.getUnderlyingPrice(mToken)
        price           scaled 1e(36 - d)

    Two identities follow, neither needing d explicitly:

        underlying_raw = mTokenBalance * exchangeRate / 1e18
        usd_1e18       = underlying_raw * price / 1e18

    The oracle's 36-d convention exists so d cancels. That is why USD
    values land at 1e18 for every token.

    Confirmed empirically 2026-08-15: derived and reported liquidity
    agreed to a ratio of 1.000000 on wallet 0xAA503ae3.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from web3 import Web3

from . import config

logger = logging.getLogger(__name__)

WAD = config.WAD

COMPTROLLER_ABI = [
    {"inputs": [{"name": "account", "type": "address"}],
     "name": "getAssetsIn",
     "outputs": [{"name": "", "type": "address[]"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "account", "type": "address"}],
     "name": "getAccountLiquidity",
     "outputs": [{"name": "error", "type": "uint256"},
                 {"name": "liquidity", "type": "uint256"},
                 {"name": "shortfall", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "oracle",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
]

MARKETS_ABI_2 = [
    {"inputs": [{"name": "", "type": "address"}], "name": "markets",
     "outputs": [{"name": "isListed", "type": "bool"},
                 {"name": "collateralFactorMantissa", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]

MARKETS_ABI_3 = [
    {"inputs": [{"name": "", "type": "address"}], "name": "markets",
     "outputs": [{"name": "isListed", "type": "bool"},
                 {"name": "collateralFactorMantissa", "type": "uint256"},
                 {"name": "isComped", "type": "bool"}],
     "stateMutability": "view", "type": "function"},
]

MTOKEN_ABI = [
    {"inputs": [{"name": "account", "type": "address"}],
     "name": "getAccountSnapshot",
     "outputs": [{"name": "error", "type": "uint256"},
                 {"name": "mTokenBalance", "type": "uint256"},
                 {"name": "borrowBalance", "type": "uint256"},
                 {"name": "exchangeRateMantissa", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "symbol",
     "outputs": [{"name": "", "type": "string"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "underlying",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
]

ORACLE_ABI = [
    {"inputs": [{"name": "mToken", "type": "address"}],
     "name": "getUnderlyingPrice",
     "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]

ERC20_ABI = [
    {"inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}],
     "stateMutability": "view", "type": "function"},
]


@dataclass
class MarketPosition:
    """A wallet's position in one Moonwell market."""
    market_address: str
    symbol: str
    supplied_underlying: float
    borrowed_underlying: float
    collateral_usd: float
    debt_usd: float
    collateral_factor: Optional[float]

    @property
    def weighted_collateral_usd(self) -> float:
        if self.collateral_factor is None:
            return 0.0
        return self.collateral_usd * self.collateral_factor


@dataclass
class WalletPosition:
    """A wallet's complete state across all Moonwell markets."""
    wallet_address: str
    block_number: int
    markets: List[MarketPosition] = field(default_factory=list)
    reported_liquidity_usd: float = 0.0
    reported_shortfall_usd: float = 0.0

    @property
    def total_collateral_usd(self) -> float:
        return sum(m.collateral_usd for m in self.markets)

    @property
    def total_weighted_collateral_usd(self) -> float:
        return sum(m.weighted_collateral_usd for m in self.markets)

    @property
    def total_debt_usd(self) -> float:
        return sum(m.debt_usd for m in self.markets)

    @property
    def is_underwater(self) -> bool:
        return self.reported_shortfall_usd > 0

    @property
    def market_count(self) -> int:
        """Markets with a non-zero supply or borrow."""
        return len(self.markets)


class BaseRPCClient:
    """Reads Moonwell wallet state from Base."""

    def __init__(self, rpc_url: Optional[str] = None,
                 comptroller: Optional[str] = None,
                 pause: float = 0.0, max_retries: int = 5):
        self.rpc_url = rpc_url or config.RPC_URL
        self.comptroller_address = comptroller or config.COMPTROLLER
        self.pause = pause
        self.max_retries = max_retries

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError("Cannot connect to " + self.rpc_url)

        chain_id = self.w3.eth.chain_id
        if chain_id != config.CHAIN_ID:
            raise ValueError(
                "Connected to chain " + str(chain_id) + ", expected "
                + str(config.CHAIN_ID) + " (Base mainnet). "
                "Moonwell has no Base testnet deployment."
            )

        self.comptroller = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.comptroller_address),
            abi=COMPTROLLER_ABI,
        )

        self._oracle = None
        self._markets_abi = None
        self._decimals_cache: Dict[str, int] = {}
        self._symbol_cache: Dict[str, str] = {}
        self._cf_cache: Dict[str, Optional[int]] = {}

    # -- internals ---------------------------------------------------------

    def _call(self, fn, *args):
        """Call a contract function, backing off on rate limits."""
        delay = 1.0
        for _ in range(self.max_retries):
            try:
                if self.pause:
                    time.sleep(self.pause)
                return fn(*args).call()
            except Exception as exc:
                if "429" in str(exc) or "Too Many Requests" in str(exc):
                    logger.warning("rate limited, waiting %.0fs", delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("Rate limited after " + str(self.max_retries)
                           + " retries on " + self.rpc_url)

    @property
    def oracle(self):
        if self._oracle is None:
            addr = self._call(self.comptroller.functions.oracle)
            self._oracle = self.w3.eth.contract(
                address=Web3.to_checksum_address(addr), abi=ORACLE_ABI
            )
        return self._oracle

    def _collateral_factor(self, market: str) -> Optional[int]:
        """Collateral factor mantissa, cached. Handles both fork variants."""
        if market in self._cf_cache:
            return self._cf_cache[market]

        candidates = ([self._markets_abi] if self._markets_abi
                      else [MARKETS_ABI_2, MARKETS_ABI_3])

        for abi in candidates:
            try:
                c = self.w3.eth.contract(
                    address=Web3.to_checksum_address(self.comptroller_address),
                    abi=abi,
                )
                result = self._call(c.functions.markets,
                                    Web3.to_checksum_address(market))
                self._markets_abi = abi
                self._cf_cache[market] = int(result[1])
                return self._cf_cache[market]
            except Exception:
                continue

        logger.warning("Could not read collateral factor for %s", market)
        self._cf_cache[market] = None
        return None

    def _decimals(self, market: str, mtoken) -> int:
        if market in self._decimals_cache:
            return self._decimals_cache[market]
        try:
            underlying = self._call(mtoken.functions.underlying)
            erc20 = self.w3.eth.contract(
                address=Web3.to_checksum_address(underlying), abi=ERC20_ABI
            )
            d = int(self._call(erc20.functions.decimals))
        except Exception:
            d = 18
        self._decimals_cache[market] = d
        return d

    def _symbol(self, market: str, mtoken) -> str:
        if market in self._symbol_cache:
            return self._symbol_cache[market]
        try:
            s = self._call(mtoken.functions.symbol)
        except Exception:
            s = market[:10]
        self._symbol_cache[market] = s
        return s

    # -- public API --------------------------------------------------------

    def get_latest_block(self) -> int:
        return self.w3.eth.block_number

    def get_account_liquidity(self, wallet: str) -> Dict[str, float]:
        """Remaining borrowing capacity (liquidity) or deficit (shortfall)."""
        addr = Web3.to_checksum_address(wallet)
        error, liquidity, shortfall = self._call(
            self.comptroller.functions.getAccountLiquidity, addr
        )
        if error != 0:
            raise RuntimeError("Comptroller error " + str(error))
        return {
            "liquidity_usd": liquidity / WAD,
            "shortfall_usd": shortfall / WAD,
        }

    def get_wallet_position(self, wallet: str) -> WalletPosition:
        """
        Full position across every market the wallet has entered.

        Markets with no supply and no borrow are skipped: getAssetsIn
        returns markets a wallet has ENABLED, not ones it has a position
        in, and the empties are usually the majority.
        """
        addr = Web3.to_checksum_address(wallet)

        position = WalletPosition(
            wallet_address=addr,
            block_number=self.get_latest_block(),
        )

        entered = self._call(self.comptroller.functions.getAssetsIn, addr)

        for market in entered:
            market_cs = Web3.to_checksum_address(market)
            mtoken = self.w3.eth.contract(address=market_cs, abi=MTOKEN_ABI)

            error, m_bal, borrow_bal, exch_rate = self._call(
                mtoken.functions.getAccountSnapshot, addr
            )
            if error != 0:
                logger.warning("snapshot error %s on %s", error, market_cs)
                continue

            if m_bal == 0 and borrow_bal == 0:
                continue

            d = self._decimals(market_cs, mtoken)
            symbol = self._symbol(market_cs, mtoken)
            price = self._call(self.oracle.functions.getUnderlyingPrice,
                               market_cs)
            cf = self._collateral_factor(market_cs)

            supplied_raw = m_bal * exch_rate // WAD
            collateral_usd = supplied_raw * price // WAD
            debt_usd = borrow_bal * price // WAD

            position.markets.append(MarketPosition(
                market_address=market_cs,
                symbol=symbol,
                supplied_underlying=supplied_raw / (10 ** d),
                borrowed_underlying=borrow_bal / (10 ** d),
                collateral_usd=collateral_usd / WAD,
                debt_usd=debt_usd / WAD,
                collateral_factor=(cf / WAD) if cf is not None else None,
            ))

        liq = self.get_account_liquidity(addr)
        position.reported_liquidity_usd = liq["liquidity_usd"]
        position.reported_shortfall_usd = liq["shortfall_usd"]

        return position