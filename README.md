# SCORE

**On-chain credit intelligence.**

SCORE reads a wallet position from a Base lending protocol and returns a
decomposed credit assessment in under 200 milliseconds.

Traditional credit is an information problem: the lender does not know who
the borrower is. DeFi lending discards identity entirely and substitutes
overcollateralization, which works and which restricts the entire sector to
borrowers who already hold more capital than they wish to borrow. What DeFi
gained in the exchange is a complete, public, permanent record of every
borrower's conduct. SCORE is built on the wager that for predicting default,
conduct is the part that matters.

## Status

Phase 0, week 2. Working against Moonwell on Base mainnet.

Implemented:

- Position reader for all Moonwell markets, batched through Multicall3
- Point-in-time credit features with directional risk detection
- 13 tests passing, including a live latency gate

Measured:

| Metric | Value |
|---|---|
| Score latency, p95 | 173 ms |
| Score latency, p50 | 156 ms |
| Network round trips per score | 1 |
| Phase 0 target | 500 ms |

The client began at 1683 ms p95 across roughly twelve sequential eth_call
round trips. Batching every read into a single Multicall3 aggregate3 brought
that to 173 ms, which is within 7 ms of a single network round trip to the
RPC provider. Correctness was held fixed by a test comparing the client's
derived liquidity against the Comptroller's own independent on-chain
computation.

## Features

Point-in-time features are deliberately interpretable. A credit decision
must be explainable to the borrower it affects, so the inputs cannot be
opaque.

- **capacity_used** - debt divided by risk-weighted collateral. This is the
  ratio the protocol enforces; it reaches 1.0 exactly at liquidation. A
  better risk measure than raw LTV, which ignores collateral factors.
- **price_move_to_liquidation** - the fractional adverse price move that
  would trigger liquidation.
- **volatility_mismatch** - true when collateral and debt sit in different
  assets, so the position carries directional price risk beyond its leverage.
  A wallet holding stable collateral against volatile debt is short that
  asset and can be liquidated by a price rise. Conventional leverage metrics
  do not reveal this.
- **exposure_usd** - outstanding debt, corresponding to EAD in the Basel
  expected-loss decomposition.

## Verified facts

Values confirmed against primary sources rather than assumed:

- Moonwell Comptroller on Base: 0xfBb21d0380beE3312B33c4353c8936a0F13EF26C
- Moonwell has no Base testnet deployment. Reads run against mainnet, which
  is safe because eth_call requires no transaction, gas, or signature.
- Comptroller USD values are scaled by 1e18. Confirmed empirically: liquidity
  derived from raw token balances and oracle prices agreed with the
  Comptroller's reported figure to a ratio of 1.000000.

## Quick start

    pip install -r requirements.txt

Create a .env file with a Base mainnet RPC endpoint:

    BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY

The public endpoint at mainnet.base.org will rate-limit under normal use.

Run the tests:

    pytest tests/ -m "not live"    # unit tests, no network
    pytest tests/ -m live -s       # live latency and correctness gates

## Roadmap

- **Weeks 2-3** REST scoring endpoint
- **Weeks 4-5** On-chain score storage contract
- **Weeks 6-7** Lender validation
- **Week 8** Base Ecosystem Fund application

## Research foundation

The approach follows Achutha, M., Hegde, B. R., and Das, B. (2026),
"Transaction graph-based predictive hurdle model for credit scoring in DeFi
lending protocols," International Journal of Data Science and Analytics,
22, 124. https://doi.org/10.1007/s41060-026-01097-7

On Compound V2 data spanning 340,737 transactions and 37,332 wallets, that
work reported PD discrimination of 0.8658 AUC-ROC and concentrated realized
risk at roughly fifty times the baseline liquidation rate within the top 100
scored wallets. SCORE adapts the method for real-time scoring on Base.

A companion book documenting the build is drafted in book/.

## License

MIT