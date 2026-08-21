"""
src/base/rpc.py - Read wallet positions from Moonwell on Base.

Every read is batched through Multicall3, which executes many contract
calls inside a single eth_call. A wallet score costs ONE network round
trip rather than one per contract read. Multicall3 also guarantees every
value comes from the same block, which sequential calls do not.

Scaling, the only subtle arithmetic:

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

    The oracle's 36-d convention exists so d cancels. Confirmed
    empirically 2026-08-15: derived and reported liquidity agreed to a
    ratio of 1.000000 on wallet 0xAA503ae3.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from eth_abi import decode as abi_decode
from web3 import Web3

from . import config

logger = logging.getLogger(__name__)

WAD = config.WAD

# Deterministic CREATE2 deployment: identical on every EVM chain.
# Verified 2026-08-15 against mds1/multicall3 and Basescan.
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"

MULTICALL3_ABI = [
    {"inputs": [{"components": [
        {"name": "target", "type": "address"},
        {"name": "allowFailure", "type": "bool"},
        {"name": "callData", "type": "bytes"}],
        "name": "calls", "type": "tuple[]"}],
     "name": "aggregate3",
     "outputs": [{"components": [
         {"name": "success", "type": "bool"},
         {"name": "returnData", "type": "bytes"}],
         "name": "returnData", "type": "tuple[]"}],
     "stateMutability": "payable", "type": "function"},
    {"inputs": [], "name": "getBlockNumber",
     "outputs": [{"name": "blockNumber", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]

COMPTROLLER_ABI = [
    {"inputs": [], "name": "getAllMarkets",
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
    {"inputs": [{"name": "", "type": "address"}], "name": "markets",
     "outputs": [{"name": "isListed", "type": "bool"},
                 {"name": "collateralFactorMantissa", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "account", "type": "address"}],
     "name": "getAssetsIn",
     "outputs": [{"name": "", "type": "address[]"}],
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
    is_entered: bool = True
    """Whether the wallet has entered this market via enterMarkets. Only
    entered markets count toward the protocol's own getAccountLiquidity;
    a supplied-but-not-entered balance is real collateral_usd but not
    usable collateral, and must not be weighted as if it were."""

    @property
    def weighted_collateral_usd(self) -> float:
        if self.collateral_factor is None or not self.is_entered:
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
        return len(self.markets)


@dataclass
class MarketMeta:
    """Static per-market data. Fetched once, reused across wallets."""
    address: str
    symbol: str
    decimals: int
    collateral_factor: Optional[float]


class BaseRPCClient:
    """Reads Moonwell wallet state from Base, batched via Multicall3."""

    def __init__(self, rpc_url: Optional[str] = None,
                 comptroller: Optional[str] = None):
        self.rpc_url = rpc_url or config.RPC_URL
        self.comptroller_address = Web3.to_checksum_address(
            comptroller or config.COMPTROLLER
        )

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

        self.multicall = self.w3.eth.contract(
            address=Web3.to_checksum_address(MULTICALL3), abi=MULTICALL3_ABI
        )
        self.comptroller = self.w3.eth.contract(
            address=self.comptroller_address, abi=COMPTROLLER_ABI
        )

        self._meta: Optional[Dict[str, MarketMeta]] = None
        self._oracle_address: Optional[str] = None

    # -- encoding helpers --------------------------------------------------

    @staticmethod
    def _encode(contract, fn_name: str, args: Optional[list] = None) -> str:
        """Calldata for a function, tolerating web3 v6/v7 API differences."""
        args = args or []
        try:
            return contract.encode_abi(fn_name, args)
        except (AttributeError, TypeError):
            return contract.encodeABI(fn_name=fn_name, args=args)

    def _aggregate(self, calls: List[Tuple[str, bool, str]]
                   ) -> List[Tuple[bool, bytes]]:
        """
        Execute many contract calls in ONE eth_call.

        Each call is (target, allow_failure, calldata). Results come back
        in order as (success, return_data). Every value is read at the
        same block, which sequential calls cannot guarantee.
        """
        if not calls:
            return []
        return self.multicall.functions.aggregate3(calls).call()

    # -- warmup ------------------------------------------------------------

    def _load_market_meta(self) -> Dict[str, MarketMeta]:
        """
        Fetch static per-market data: symbol, decimals, collateral factor.

        Three round trips, paid once per client. Scoring N wallets after
        this costs N round trips, not N * markets.
        """
        try:
            markets = self.comptroller.functions.getAllMarkets().call()
        except Exception:
            logger.warning("getAllMarkets failed; falling back to config")
            markets = list(config.MARKETS.values())

        markets = [Web3.to_checksum_address(m) for m in markets]
        mtoken = self.w3.eth.contract(address=markets[0], abi=MTOKEN_ABI)

        # Batch 1: symbol, underlying, and collateral factor for every market.
        calls: List[Tuple[str, bool, str]] = []
        for m in markets:
            calls.append((m, True, self._encode(mtoken, "symbol")))
            calls.append((m, True, self._encode(mtoken, "underlying")))
            calls.append((self.comptroller_address, True,
                          self._encode(self.comptroller, "markets", [m])))

        results = self._aggregate(calls)

        symbols: Dict[str, str] = {}
        underlyings: Dict[str, Optional[str]] = {}
        factors: Dict[str, Optional[float]] = {}

        for i, m in enumerate(markets):
            ok_sym, sym_data = results[i * 3]
            ok_und, und_data = results[i * 3 + 1]
            ok_mkt, mkt_data = results[i * 3 + 2]

            symbols[m] = (abi_decode(["string"], sym_data)[0]
                          if ok_sym and sym_data else m[:10])

            underlyings[m] = (abi_decode(["address"], und_data)[0]
                              if ok_und and und_data else None)

            # Moonwell may return (bool, uint) or Compound's (bool, uint, bool).
            # Byte length disambiguates: 64 vs 96.
            if ok_mkt and mkt_data:
                types = (["bool", "uint256", "bool"] if len(mkt_data) >= 96
                         else ["bool", "uint256"])
                factors[m] = abi_decode(types, mkt_data)[1] / WAD
            else:
                factors[m] = None

        # Batch 2: decimals for each distinct underlying token.
        distinct = sorted({u for u in underlyings.values() if u})
        erc20 = (self.w3.eth.contract(
            address=Web3.to_checksum_address(distinct[0]), abi=ERC20_ABI)
            if distinct else None)

        decimals_by_token: Dict[str, int] = {}
        if erc20 is not None:
            dec_calls = [(Web3.to_checksum_address(u), True,
                          self._encode(erc20, "decimals")) for u in distinct]
            for u, (ok, data) in zip(distinct, self._aggregate(dec_calls)):
                decimals_by_token[u] = (abi_decode(["uint8"], data)[0]
                                        if ok and data else 18)

        meta = {}
        for m in markets:
            u = underlyings[m]
            meta[m] = MarketMeta(
                address=m,
                symbol=symbols[m],
                decimals=decimals_by_token.get(u, 18),
                collateral_factor=factors[m],
            )

        logger.info("Loaded metadata for %d markets", len(meta))
        return meta

    @property
    def market_meta(self) -> Dict[str, MarketMeta]:
        if self._meta is None:
            self._meta = self._load_market_meta()
        return self._meta

    @property
    def oracle_address(self) -> str:
        if self._oracle_address is None:
            self._oracle_address = Web3.to_checksum_address(
                self.comptroller.functions.oracle().call()
            )
        return self._oracle_address

    # -- public API --------------------------------------------------------

    def get_latest_block(self) -> int:
        return self.w3.eth.block_number

    def get_account_liquidity(self, wallet: str) -> Dict[str, float]:
        """Remaining borrowing capacity, or deficit if underwater."""
        addr = Web3.to_checksum_address(wallet)
        error, liquidity, shortfall = (
            self.comptroller.functions.getAccountLiquidity(addr).call()
        )
        if error != 0:
            raise RuntimeError("Comptroller error " + str(error))
        return {"liquidity_usd": liquidity / WAD,
                "shortfall_usd": shortfall / WAD}

    def get_wallet_position(self, wallet: str) -> WalletPosition:
        """
        Full position across every Moonwell market, in ONE round trip.

        Batches every snapshot, every price, the account liquidity, the
        entered-markets set, and the block number into a single aggregate3
        call. Prices do not depend on the wallet, so they ride along at no
        extra cost.
        """
        addr = Web3.to_checksum_address(wallet)
        meta = self.market_meta
        markets = list(meta.keys())

        mtoken = self.w3.eth.contract(address=markets[0], abi=MTOKEN_ABI)
        oracle = self.w3.eth.contract(
            address=self.oracle_address, abi=ORACLE_ABI
        )

        calls: List[Tuple[str, bool, str]] = []

        # Block first, so it is unambiguous which block everything is from.
        calls.append((Web3.to_checksum_address(MULTICALL3), False,
                      self._encode(self.multicall, "getBlockNumber")))
        calls.append((self.comptroller_address, False,
                      self._encode(self.comptroller,
                                   "getAccountLiquidity", [addr])))
        # getAccountLiquidity only counts markets the wallet has ENTERED via
        # enterMarkets - a supplied-but-not-entered balance is real
        # collateral_usd but not usable collateral. Fetched here so every
        # MarketPosition below can be tagged correctly.
        calls.append((self.comptroller_address, False,
                      self._encode(self.comptroller, "getAssetsIn", [addr])))
        for m in markets:
            calls.append((m, True, self._encode(
                mtoken, "getAccountSnapshot", [addr])))
        for m in markets:
            calls.append((self.oracle_address, True, self._encode(
                oracle, "getUnderlyingPrice", [m])))

        results = self._aggregate(calls)

        block_number = abi_decode(["uint256"], results[0][1])[0]
        _err, liquidity, shortfall = abi_decode(
            ["uint256", "uint256", "uint256"], results[1][1]
        )
        entered = {
            Web3.to_checksum_address(a)
            for a in abi_decode(["address[]"], results[2][1])[0]
        }

        n = len(markets)
        snapshots = results[3:3 + n]
        prices = results[3 + n:3 + 2 * n]

        position = WalletPosition(
            wallet_address=addr,
            block_number=block_number,
            reported_liquidity_usd=liquidity / WAD,
            reported_shortfall_usd=shortfall / WAD,
        )

        for i, m in enumerate(markets):
            ok_snap, snap_data = snapshots[i]
            if not ok_snap or not snap_data:
                continue

            error, m_bal, borrow_bal, exch_rate = abi_decode(
                ["uint256", "uint256", "uint256", "uint256"], snap_data
            )
            if error != 0:
                logger.warning("snapshot error %s on %s", error, m)
                continue

            # getAllMarkets returns every market; most are empty for any
            # given wallet. Skipping them costs nothing since the calls
            # were already batched.
            if m_bal == 0 and borrow_bal == 0:
                continue

            ok_price, price_data = prices[i]
            if not ok_price or not price_data:
                logger.warning("no price for %s; skipping", m)
                continue
            price = abi_decode(["uint256"], price_data)[0]

            info = meta[m]
            supplied_raw = m_bal * exch_rate // WAD
            collateral_usd = supplied_raw * price // WAD
            debt_usd = borrow_bal * price // WAD

            position.markets.append(MarketPosition(
                market_address=m,
                symbol=info.symbol,
                supplied_underlying=supplied_raw / (10 ** info.decimals),
                borrowed_underlying=borrow_bal / (10 ** info.decimals),
                collateral_usd=collateral_usd / WAD,
                debt_usd=debt_usd / WAD,
                collateral_factor=info.collateral_factor,
                is_entered=m in entered,
            ))

        return position