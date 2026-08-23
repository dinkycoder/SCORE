# Morpho Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read a wallet's position on one specific, verified Morpho Blue market (cbBTC/USDC on Base) and produce the same `CreditFeatures` output the Moonwell path produces, proving SCORE's method ports to an isolated-market accounting model.

**Architecture:** A new `src/morpho/` package mirrors `src/base/`'s shape but reads a fundamentally different contract interface (Morpho Blue's per-market `position()`/`market()`, not Compound's Comptroller). Its output is shaped as the *existing* `WalletPosition`/`MarketPosition` dataclasses from `src/base/rpc.py`, so `src/scoring/features.py::extract_features` runs completely unchanged.

**Tech Stack:** Python, web3.py 7.5.0, pytest, Multicall3 (same deterministic address as the Moonwell path).

## Global Constraints

- Single market only: Morpho Blue cbBTC/USDC on Base. No market discovery/enumeration in this plan.
- Reuse `base.rpc.WalletPosition` / `base.rpc.MarketPosition` / `scoring.features.extract_features` unchanged — no new feature dataclass.
- `reported_liquidity_usd`/`reported_shortfall_usd` for Morpho positions are **our own derived math**, not an independent protocol-side check (Morpho Blue has no `getAccountLiquidity` equivalent) — this must be stated in code comments, not left implicit.
- Fail loud on any decode/call error — no silent zeroing (matches every other client in this codebase).
- Full spec: `docs/superpowers/specs/2026-08-23-morpho-reader-design.md`.

---

### Task 1: Morpho shares-to-assets conversion

Morpho Blue stores a borrower's debt as `borrowShares`, not a raw amount — this task implements the exact conversion Morpho itself uses (`SharesMathLib.toAssetsUp`), so later tasks have a tested, correct building block.

**Files:**
- Create: `src/morpho/__init__.py`
- Create: `src/morpho/rpc.py`
- Test: `tests/test_morpho_rpc.py`

**Interfaces:**
- Produces: `shares_to_assets_up(shares: int, total_assets: int, total_shares: int) -> int`

- [ ] **Step 1: Create the package and write the failing test**

Create `src/morpho/__init__.py` (empty file).

Create `tests/test_morpho_rpc.py`:

```python
"""
tests/test_morpho_rpc.py - MorphoRPCClient's own conversion/decode logic.

extract_features() itself needs no new tests here - it's reused
unchanged from the Moonwell path (see
docs/superpowers/specs/2026-08-23-morpho-reader-design.md §5). These
tests cover what's actually new: Morpho's shares math and the raw-data
-> MarketPosition conversion.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from morpho.rpc import shares_to_assets_up


def test_shares_to_assets_up_rounds_up_not_down():
    """Hand-verified: 500_000_000 shares of a 1_000_000_000-share pool
    holding 999 total assets is 499.5009... Morpho rounds UP for a
    borrower's owed amount (SharesMathLib.toAssetsUp), so this must come
    out to 500, not 499 - a wallet's debt must never be understated by
    rounding."""
    assert shares_to_assets_up(500_000_000, 999, 1_000_000_000) == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_morpho_rpc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'morpho.rpc'` or `ImportError: cannot import name 'shares_to_assets_up'`

- [ ] **Step 3: Write minimal implementation**

Create `src/morpho/rpc.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_morpho_rpc.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/morpho/__init__.py src/morpho/rpc.py tests/test_morpho_rpc.py
git commit -m "Add Morpho shares-to-assets conversion (SharesMathLib.toAssetsUp)"
```

---

### Task 2: MarketPosition construction from raw Morpho data

Converts a market's raw collateral/borrowed-assets/oracle-price into the existing `MarketPosition` dataclass, so `extract_features()` can consume it without any changes.

**Files:**
- Create: `src/morpho/config.py`
- Modify: `src/morpho/rpc.py`
- Test: `tests/test_morpho_rpc.py`

**Interfaces:**
- Consumes: `base.rpc.MarketPosition` (existing dataclass, unmodified)
- Produces: `build_market_position(market_id_hex: str, collateral_raw: int, borrowed_assets_raw: int, collateral_price_1e36: int, collateral_decimals: int, loan_decimals: int) -> MarketPosition`

- [ ] **Step 1: Write the config constants (verified 2026-08-23)**

Create `src/morpho/config.py`:

```python
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
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_morpho_rpc.py`:

```python
from morpho.rpc import build_market_position


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_morpho_rpc.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_market_position'`

- [ ] **Step 4: Write minimal implementation**

Add the two new imports to the TOP of `src/morpho/rpc.py`, alongside its
existing module docstring (no `sys.path` manipulation needed - `src/api/server.py`
and `src/scoring/features.py` both import cross-package as
`from base.rpc import ...` with no path setup of their own, because
whatever imports them already has `src/` on `sys.path`; this module
follows the same convention):

```python
from base.rpc import MarketPosition

from . import config
```

Then append the new function after `shares_to_assets_up`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_morpho_rpc.py -v`
Expected: PASS (3 tests: the Task 1 test plus these two)

- [ ] **Step 6: Commit**

```bash
git add src/morpho/config.py src/morpho/rpc.py tests/test_morpho_rpc.py
git commit -m "Add Morpho MarketPosition construction from raw market data"
```

---

### Task 3: MorphoRPCClient - live Multicall3-batched reads

The actual chain-reading client: batches `position()`, `market()`, and the oracle's `price()` into one Multicall3 call (matching `BaseRPCClient`'s one-round-trip pattern), decodes the results, and calls Tasks 1-2's functions to build a `WalletPosition`.

**Files:**
- Modify: `src/morpho/rpc.py`
- Test: `tests/test_morpho_rpc.py`

**Interfaces:**
- Consumes: `shares_to_assets_up`, `build_market_position` (Tasks 1-2); `base.rpc.WalletPosition`, `base.rpc.MULTICALL3`, `base.rpc.MULTICALL3_ABI`; `base.config.RPC_URL`, `base.config.CHAIN_ID`
- Produces: `MorphoRPCClient.get_wallet_position(wallet: str) -> WalletPosition`

- [ ] **Step 1: Write the failing live test**

Add to `tests/test_morpho_rpc.py`:

```python
import pytest


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_morpho_rpc.py -m live -v`
Expected: FAIL with `ImportError: cannot import name 'MorphoRPCClient'`

- [ ] **Step 3: Write minimal implementation**

Add these imports to the TOP of `src/morpho/rpc.py`, alongside the
imports from Task 2 (note the `base_config` alias - this module already
has a `config` name bound to its own `src/morpho/config.py` via
`from . import config` in Task 2, so the chain-level `base.config` needs
a distinct name to avoid shadowing it):

```python
from typing import List, Optional, Tuple

from eth_abi import decode as abi_decode
from web3 import Web3

from base.rpc import MULTICALL3, MULTICALL3_ABI, WalletPosition
from base import config as base_config
```

Then append the new ABI constants and client class after `build_market_position`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_morpho_rpc.py -m live -v`
Expected: PASS. If the hardcoded wallet has closed its position by execution time, use the Borrow-event-scan technique from the design spec §3/this task's test docstring to find a replacement (same situation `tests/test_latency.py`'s reference wallet hit last session).

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `pytest tests/ -q`
Expected: all prior tests still pass; new Morpho tests included in the count.

- [ ] **Step 6: Commit**

```bash
git add src/morpho/rpc.py tests/test_morpho_rpc.py
git commit -m "Add MorphoRPCClient: Multicall3-batched reads for cbBTC/USDC"
```

---

### Task 4: Boundary tests for the is_underwater derivation

Task 3 already wires `reported_liquidity_usd`/`reported_shortfall_usd` from derived math. This task adds tests proving that derivation is correct at the liquidation boundary in both directions — the exact shape of bug (`is_underwater` silently wrong) this project has hit twice already in the Moonwell path.

**Files:**
- Test: `tests/test_morpho_rpc.py`

**Interfaces:**
- Consumes: `build_market_position` (Task 2); `base.rpc.WalletPosition`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_morpho_rpc.py`:

```python
from base.rpc import WalletPosition


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
    """Debt exceeds weighted collateral (86,000 * 0.86 = 73,960 < 80,000
    borrowed) - must be flagged, not silently reported healthy the way
    the None-collateral-factor and not-entered-market bugs silently
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
```

- [ ] **Step 2: Run tests to verify they fail or pass for the right reason**

Run: `pytest tests/test_morpho_rpc.py -k "underwater" -v`
Expected: since Task 3 already implemented the derivation these tests check, this is validating existing behavior rather than driving new code (same situation as the HTTP endpoint tests from an earlier session). If both pass immediately, proceed to Step 3's mutation check instead of a further implementation step. If either fails, the Task 3 implementation has a bug - fix `get_wallet_position` (not the test) before proceeding.

- [ ] **Step 3: Prove the underwater test isn't vacuous**

Temporarily edit the test file: change `reported_shortfall_usd=max(0.0, debt - weighted)` to `reported_shortfall_usd=0.0` in `test_underwater_position_is_flagged` only, run `pytest tests/test_morpho_rpc.py -k test_underwater_position_is_flagged -v`, confirm it now FAILS (proving the assertion is actually exercising the derivation), then revert the edit and confirm it passes again.

- [ ] **Step 4: Commit**

```bash
git add tests/test_morpho_rpc.py
git commit -m "Add boundary tests for Morpho is_underwater derivation"
```

---

### Task 5: Live verification cross-check and documentation

No independent on-chain correctness check exists for Morpho (design spec §6/§8) — this task is the one-time manual cross-check the spec calls for, plus recording the outcome and the scope boundary in `docs/PHASE_0.md`.

**Files:**
- Modify: `docs/PHASE_0.md`

- [ ] **Step 1: Run the live client against the reference wallet and record the numbers**

Run:
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from morpho.rpc import MorphoRPCClient
from scoring.features import extract_features
c = MorphoRPCClient()
pos = c.get_wallet_position('0x04a9530da51Eb174153F150FfDF103B368c332E5')
f = extract_features(pos)
print(f.to_dict())
"
```
Record the printed `capacity_used`, `headroom`, `collateral_usd`, `debt_usd` values.

- [ ] **Step 2: Cross-check against an independent source**

Query Morpho's own public data — either their GraphQL API (`https://blue-api.morpho.org`, check current schema for a market/position query) or a block explorer's decoded view of the `position`/`market` calls for the same wallet and market ID — for the same wallet's collateral/borrow/health figures. Confirm they agree with Step 1's numbers within a few percent (small differences are expected from interest accrual between `market()`'s `lastUpdate` and the query time — see design spec §8). If they disagree by more than that, stop and debug before writing anything to docs — do not record an unreconciled discrepancy as if it were resolved.

- [ ] **Step 3: Update docs/PHASE_0.md**

Add a new subsection under "Status" (or wherever the existing Moonwell-reader status lives) recording:
- The Morpho reader is complete for the single cbBTC/USDC market scope (link the design spec).
- The manual cross-check result from Step 2 (source used, numbers compared, agreement within X%).
- Explicitly restate the `is_underwater`/`reported_liquidity_usd` caveat from design spec §6 - this is permanent, not a TODO.
- Explicitly restate what's still out of scope (design spec §9): market discovery, other markets, `/position` wiring, any write path, Aave.

- [ ] **Step 4: Run the complete test suite one final time**

Run: `pytest tests/ -q`
Expected: all tests pass (offline + live), matching or exceeding the pre-Task-1 count plus the new Morpho tests.

- [ ] **Step 5: Commit**

```bash
git add docs/PHASE_0.md
git commit -m "Record Morpho reader verification and scope in PHASE_0.md"
```
