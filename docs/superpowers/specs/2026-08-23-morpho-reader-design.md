# Morpho Reader — Design

> Scoped as "the Morpho reader for the demonstration venue" (PHASE_0.md's
> Phase 1 item). This is a read + feature-extraction pipeline for one
> specific Morpho Blue market on Base, proving the SCORE method ports to
> an isolated-market accounting model, not a general Morpho integration.
>
> Written: 2026-08-23

---

## 1. Why Morpho, and why this is real design work, not a port

`docs/PHASE_0.md` already recorded the reasoning for choosing Morpho as the
demonstration venue: it's the largest and (unlike Moonwell and Aave)
growing lending protocol on Base, and its isolated-market architecture is
*deliberately* chosen to prove SCORE's method generalizes beyond
Compound-family protocols, not despite that architectural distance.

That same document warned: *"`BaseRPCClient` would be rewritten against a
different accounting model, not adapted, and the verification work...
redone. This is the single largest piece of Phase 1 engineering."* This
spec confirms that and scopes the first concrete step.

## 2. Scope decision

Given Morpho Blue has no `getAllMarkets`-style enumeration and no
account-level `getAccountLiquidity` spanning positions — markets are
permissionless and isolated, identified by a `marketId` derived from
(loan token, collateral token, oracle, IRM, LLTV), and a position is
inherently per-(market, wallet) — the first version targets **one
specific, verified market**, not general market discovery. Discovery
across all of Morpho is a separate, later problem.

## 3. Target market — verified on-chain, not from a webpage

Morpho Blue core contract on Base: `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb`
(confirmed against Morpho's own docs at
`docs.morpho.org/get-started/resources/addresses/`, and confirmed to have
15,623 bytes of deployed code via `eth_getCode` on 2026-08-23).

Three candidate markets were queried directly on-chain (not trusted from
search results, since `app.morpho.org`'s market pages are a JS SPA that
doesn't render via a static fetch):

| Market | Market ID | LLTV | Supply | Borrow |
|---|---|---|---|---|
| **cbBTC/USDC (chosen)** | `0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836` | 0.86 | ~1,492,288,756 USDC | ~1,317,523,521 USDC |
| cbBTC/WETH | `0x5dffffc7d75dc5abfa8dbe6fad9cbdadf6680cbe1428bafe661497520c84a94c` | 0.915 | ~164 WETH | ~145.6 WETH |
| wstETH/USDC | `0xa066f3893b780833699043f824e5bb88b8df039886f524f62b9a1ac83cb7f1f0` | 0.86 | ~50 USDC | ~45 USDC |

cbBTC/USDC dwarfs the other two and is volatile-collateral/stable-debt —
the same shape as Moonwell's dominant pattern this project has already
built features around, making it a directly comparable target.

Only **Market ID** and **LLTV** are fixed constants to hardcode (LLTV is
immutable per market - it's literally part of what the market ID is
derived from). **Supply/Borrow are a 2026-08-23 snapshot**, recorded here
only as evidence for the market-selection reasoning above, not values to
hardcode anywhere in the implementation.

Market parameters (via `idToMarketParams`, confirmed 2026-08-23):
- loan token (USDC): `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- collateral token (cbBTC): `0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf`
- oracle: `0x663BECd10daE6C4A3Dcd89F1d76c1174199639B9`
- IRM (Adaptive Curve, shared across markets on Base): `0x46415998764C29aB2a25CbeA6254146D50D22687`
- LLTV: 0.86 (86%)

## 4. Architecture

New package `src/morpho/`, mirroring `src/base/`'s shape:

- `src/morpho/config.py` — the verified constants in §3. Reuses
  `base.config` for `RPC_URL`/`CHAIN_ID`/`WAD`, which are chain-level, not
  protocol-specific.
- `src/morpho/rpc.py` — `MorphoRPCClient`, reading this one market only.

No new HTTP endpoint in this scope. This is a reader + feature pipeline;
wiring it into `/position` is a small, separate follow-up once it's
proven, not bundled into this spec.

## 5. Key decision: reuse `WalletPosition`/`extract_features` unchanged

`MorphoRPCClient.get_wallet_position(wallet)` returns the *same*
`WalletPosition` dataclass Moonwell uses (`src/base/rpc.py`), with
`markets=[one MarketPosition]` — a single-element list representing the
one market:

- `symbol="cbBTC"`
- `collateral_factor=0.86` (the LLTV, used exactly like Moonwell's
  collateral factor in `weighted_collateral_usd`)
- `is_entered=True` always — Morpho Blue has no separate "enter market"
  step; supplying collateral to an isolated market *is* entering it.

This means `src/scoring/features.py::extract_features` needs **zero code
changes** — Morpho-sourced positions flow through the same pipeline (and
eventually the same `/position` response shape and `CreditScorer` write
path) as Moonwell ones, with no protocol-specific branching downstream.
But "zero changes" is not the same claim as "every field means the same
thing it does for Moonwell." Split by outcome:

**Reuse cleanly** (behave the way their docstrings describe, for the
reason those docstrings give): `capacity_used`, `headroom`,
`debt_rise_to_liquidation`, `degraded`, `is_underwater`. Each of these
depends on `weighted_collateral_usd` vs `debt_usd`, which is exactly what
a single-`MarketPosition` representation with `collateral_factor=LLTV`
computes correctly.

**Do NOT reuse cleanly** — computed without error, but the *value* is
degenerate or actively wrong for what the field is documented to mean:

- `volatility_mismatch` is **structurally always `False`** for every
  Morpho position from this client, regardless of the actual position.
  `extract_features` detects a mismatch by comparing the set of symbols
  with `collateral_usd > 0` against the set of symbols with `debt_usd >
  0`. Because `build_market_position` packs both collateral AND debt
  into one `MarketPosition` under a single symbol (`"cbBTC"`), those two
  sets are always the same one-element set — even for this market, which
  *is* a volatility mismatch by construction (volatile cbBTC collateral
  against stable USDC debt), exactly the case this feature exists to
  catch. Moonwell doesn't hit this because each mToken is its own
  `MarketPosition`, so collateral and debt can land on different
  symbols. This cannot be fixed without either changing
  `extract_features()` (out of scope — it's shared, unmodified code) or
  splitting a Morpho position into two synthetic `MarketPosition`s
  (a larger design change, not attempted here). It is a permanent,
  documented limitation (see `src/morpho/rpc.py`'s module docstring),
  not a bug silently shipped as a correct-looking `False`.
- `market_count` is **degenerate**, not a "concentration proxy" the way
  it is for a multi-market Moonwell wallet: it is always exactly 1 when
  this client finds a position, and 0 for a wallet with no position on
  this market at all (regardless of how diversified that wallet's
  Morpho activity is across markets this client doesn't read — recall
  §2's single-market scope).

## 6. The one place this reuse gets awkward: `is_underwater`

`WalletPosition.is_underwater` reads `reported_shortfall_usd > 0`. For
Moonwell, that value comes from the Comptroller's own independently
computed `getAccountLiquidity` call. **Morpho Blue has no equivalent** —
confirmed by reading its interface directly: `position(id, user)` returns
only raw `supplyShares`/`borrowShares`/`collateral`, the same kind of raw
data `getAccountSnapshot` gives for Moonwell, not a second, independent
health computation. Health is checked internally during
borrow/withdraw and never exposed as a public view.

If `reported_liquidity_usd`/`reported_shortfall_usd` were left at their
`0.0` default for Morpho positions, `is_underwater` would silently always
report `False` regardless of actual position health — exactly the
false-safety shape this project has spent two sessions finding and fixing
in the Moonwell path (the `None`-collateral-factor bug, the
supplied-but-not-entered-markets bug). Shipping the same shape of bug into
a brand-new protocol integration on day one would be a real failure of
everything this project has been trying to instill.

**Resolution**: for Morpho, `reported_liquidity_usd`/`reported_shortfall_usd`
are set from our *own* derived `weighted_collateral_usd - debt_usd`, not an
independent source. This makes `is_underwater` behave correctly, but it is
**not the same verification strength as Moonwell's** — it's our own math
duplicated into that slot, not a protocol-side cross-check. This gets
stated explicitly in `MorphoRPCClient`'s module docstring and in
`docs/PHASE_0.md`, not left implicit for someone to discover later by
reading source.

## 7. Error handling

- An oracle call failure, or a decode error on `position()`/`market()`,
  raises rather than silently zeroing out a value — the same fail-loud
  posture as the rest of this codebase (compare `sanctions.py`'s
  `StaleListError`/`ListUnavailableError`, or `rpc.py`'s handling of a
  failed `getAccountLiquidity` call).
- Market/oracle/token addresses are hardcoded, verified constants (same
  pattern as `COMPTROLLER` in `base/config.py`) — no discovery or
  enumeration logic, matching the single-market scope from §2.

## 8. Testing plan

- **Offline**: unit tests for `MorphoRPCClient`'s own decode/scaling logic
  (raw shares/collateral → `MarketPosition`, oracle price scaling) against
  hand-computed synthetic values — mirrors `test_features.py`'s pattern.
  `extract_features` needs no CODE changes, since it's unchanged (§5), but
  it still needs at least one test that actually calls it on a
  Morpho-sourced `WalletPosition` — an early version of this plan shipped
  without one, which is exactly how the `volatility_mismatch` limitation
  in §5 went undetected across 5 individual task reviews. That test now
  exists (`tests/test_morpho_rpc.py::test_extract_features_on_morpho_position`)
  and asserts the full resulting `CreditFeatures`, including
  `volatility_mismatch is False` as an explicit, intentional assertion of
  the known limitation, not a silent gap.
- **Live** (marked `live`, same convention as the existing Moonwell
  tests): reads the real cbBTC/USDC market for a real wallet with an open
  position, confirms no errors and sane, internally consistent output.
- **No independent on-chain correctness check exists for Morpho** (§6) —
  a real, permanent limitation, not a gap to silently paper over. A
  one-time manual cross-check against Morpho's own app for a real wallet
  will be done during implementation as external sanity-checking evidence
  (same spirit as the original Moonwell scaling verification), recorded in
  `docs/PHASE_0.md`'s verification notes — not claimed as an automated
  test, since no automatable independent source exists to test against.
- The oracle's documented `1e36`-scaled collateral-in-loan-token price
  convention (per Morpho's `IOracle` interface) gets confirmed empirically
  during implementation against the real cbBTC/USDC market, the same way
  every other scaling assumption in this codebase has been confirmed
  rather than assumed.

## 9. Explicitly out of scope for this spec

- Market discovery/enumeration across all of Morpho.
- Any other Morpho market besides cbBTC/USDC.
- Wiring into the `/position` HTTP endpoint or `/capabilities`.
- Any write path (`CreditScorer` integration) for Morpho-sourced scores.
- Aave. Contingent on a specific lender using it, per PHASE_0.md; not
  triggered by this work.
