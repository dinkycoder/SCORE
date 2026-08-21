# SCORE

**On-chain credit intelligence.**

SCORE reads a wallet's position from a Base lending protocol and returns
verified point-in-time solvency features in under 200 milliseconds.

Traditional credit is an information problem: the lender does not know who
the borrower is. DeFi lending discards identity entirely and substitutes
overcollateralization, which works and which restricts the entire sector to
borrowers already holding more capital than they wish to borrow. What DeFi
gained in the exchange is a complete, public, permanent record of every
borrower's conduct. SCORE is built on the wager that for predicting default,
conduct is the part that matters.

## What this is, and what it is not

**Implemented.** Real-time solvency triage. Live position reconstruction
across every market of a lending protocol, with arithmetic verified against
the protocol's own on-chain computation, exposed through an interpretable
feature set.

**Not implemented.** Probability of default, loss given default, and any
trained model. No accuracy figures are claimed for SCORE, because no model
has been fitted.

The distinction is stated plainly because it is the difference between a
solvency check and a credit score. The target architecture is the hurdle
framework of Achutha et al. (2026), which decomposes expected loss into
PD, LGD, and EAD. Phase 0 implements the exposure component and the live
data infrastructure beneath all three. The two modelled components require
liquidation labels over a defined label period, which requires event
extraction that has not been built. See `docs/PHASE_0.md` for why that
sequencing was chosen deliberately.

## Measured

| Metric | Value |
|---|---|
| Position read latency, p95 | 173 ms |
| Position read latency, p50 | 156 ms |
| Network round trips per read | 1 |
| Phase 0 target | 500 ms |

The client began at 1683 ms p95 across roughly twelve sequential eth_call
round trips. Batching every read into a single Multicall3 aggregate3 call
brought that to 173 ms, which is within 7 ms of a single network round trip
to the RPC provider. Correctness was held fixed throughout by a test
comparing the client's derived liquidity against the Comptroller's own
independent on-chain computation.

## Features

Features are deliberately interpretable. A credit decision must be
explicable to the borrower it affects (CFPB Circular 2022-03), so the
inputs cannot be opaque.

- **capacity_used** - debt divided by risk-weighted collateral. This is the
  ratio the protocol enforces; it reaches 1.0 exactly at liquidation. A
  better risk measure than raw LTV, which ignores collateral factors and
  understated leverage on the reference wallet by nine percentage points.
- **headroom** (`1 - capacity_used`) - equivalently, the fractional
  *collateral*-price drop that would trigger liquidation, holding debt
  price fixed.
- **debt_rise_to_liquidation** - the fractional *debt*-price rise that
  would trigger liquidation, holding collateral price fixed. This is a
  different, larger number than headroom for any leveraged position, not
  an alternate phrasing of it - they answer different stress tests.
- **volatility_mismatch** - true when collateral and debt sit in different
  assets, so the position carries directional price risk beyond its
  leverage. A wallet holding stable collateral against volatile debt is
  short that asset and can be liquidated by a price *rise*. Conventional
  leverage metrics do not reveal this. This feature does not appear in the
  source literature; it came from examining a live position.
- **exposure_usd** - outstanding debt, corresponding to EAD in the Basel
  expected-loss decomposition.

## Verified facts

Values confirmed against primary sources rather than assumed:

- Moonwell Comptroller on Base: `0xfBb21d0380beE3312B33c4353c8936a0F13EF26C`
- Moonwell has no Base testnet deployment. Reads run against mainnet, which
  is safe because `eth_call` requires no transaction, gas, or signature.
- Comptroller USD values are scaled by 1e18. Confirmed empirically:
  liquidity derived from raw token balances and oracle prices agreed with
  the Comptroller's reported figure to a ratio of 1.000000.

## Quick start

```
pip install -r requirements.txt
```

Create a `.env` file with a Base mainnet RPC endpoint:

```
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
```

The public endpoint at `mainnet.base.org` will rate-limit under normal use;
reading one position costs roughly twelve contract calls before batching.

Run the tests:

```
pytest tests/ -m "not live"    # unit tests, no network
pytest tests/ -m live -s       # live latency and correctness gates
```

## Endpoints

| Route | Returns |
|---|---|
| `GET /health` | Service and chain status |
| `GET /capabilities` | Explicit list of what is and is not implemented |
| `GET /position/<wallet>` | Point-in-time solvency features and per-market detail |

## Roadmap

| Stage | Work |
|---|---|
| Weeks 2-3 | HTTP interface over the verified feature pipeline |
| Weeks 4-5 | On-chain storage contract |
| Weeks 6-7 | Lender validation |
| Week 8 | Base Ecosystem Fund application |

Beyond Phase 0: event-log extraction for behavioural history, liquidation
labels over a defined label period, and the PD and LGD stages of the hurdle
model.

## Open questions

Recorded because they bear on feasibility rather than merely on schedule:

1. How many liquidation events exist on Moonwell Base over a usable label
   period? This determines whether PD and LGD are estimable at all.
2. What is the scoreable universe of wallets holding open positions?
3. What re-scoring cadence do lenders actually require, and what does that
   cost against RPC compute-unit pricing?

## Research foundation

The approach follows Achutha, M., Hegde, B. R., & Das, B. (2026).
Transaction graph-based predictive hurdle model for credit scoring in DeFi
lending protocols. *International Journal of Data Science and Analytics, 22*,
124. https://doi.org/10.1007/s41060-026-01097-7

On Compound V2 data spanning 340,737 transactions and 37,332 wallets, that
work reported PD discrimination of 0.8658 AUC-ROC and concentrated realised
risk at approximately fifty times the baseline liquidation rate within the
top 100 scored wallets. **Those are the authors' figures on their dataset,
not SCORE results.** SCORE adapts the framework for real-time scoring on
Base.

A companion book documenting the build is drafted in `book/`.

## License

MIT
