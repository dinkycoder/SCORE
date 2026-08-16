# SCORE Phase 0

## Scope decision

Phase 0 delivers **real-time solvency triage**, not a trained credit model.

The hurdle framework of Achutha et al. (2026) decomposes expected loss into
probability of default, loss given default, and exposure at default. SCORE
adopts that framework as its target architecture. Phase 0 implements the
exposure component and the live-data infrastructure beneath all three. The
two modelled components require liquidation labels over a defined label
period, which requires event-log extraction that has not been built.

This is stated as a decision rather than an omission. Two considerations
drive it:

1. Label extraction is the longest pole. Achutha et al. worked from six
   years of Compound V2 history and, after validity and positive-severity
   filtering, trained their loss-severity stage on 139 wallets. Moonwell on
   Base is younger and smaller. Whether sufficient liquidation events exist
   to fit a severity model is an open empirical question, and discovering
   the answer in week seven would be fatal to the week eight application.

2. Solvency triage is defensible standing alone: verified position
   arithmetic, sub-200ms latency, and a directional-risk feature the source
   literature does not contain.

The claim made to lenders and to the Base Ecosystem Fund is therefore:
infrastructure built and verified, PD and LGD on the roadmap with a stated
extraction plan. Not a decomposition half-implemented.

## Corrections to the original plan

Two assumptions in the first draft of this document did not survive contact
with the protocol.

**Base Sepolia.** The original plan specified testnet-only development.
Moonwell has no Base testnet deployment. Reads run against Base mainnet,
which is safe because eth_call requires no transaction, gas, or signature.
Contract deployment in weeks 4-5 may still target Sepolia.

**Latency budget.** The original plan assumed the public RPC endpoint would
suffice. Reading one position costs roughly twelve contract calls; forty-five
calls in succession returned HTTP 429. A dedicated endpoint is a
prerequisite, not an optimisation.

## Status

### Complete

- Base RPC client reading full wallet positions across all Moonwell markets
- All reads batched through Multicall3: one network round trip per wallet
- Point-in-time solvency features, including capacity utilisation,
  price-move-to-liquidation, and volatility mismatch
- Position arithmetic verified against the Comptroller's own on-chain
  computation to a ratio of 1.000000
- 13 tests, including a live latency gate and a live correctness gate

### Measured

| Metric | Value | Target |
|---|---|---|
| Score latency p95 | 173 ms | 500 ms |
| Score latency p50 | 156 ms | - |
| Round trips per score | 1 | - |

Baseline before batching was 1683 ms p95 across roughly twelve sequential
calls. A single round trip to the RPC provider measures 149 ms, so the
current figure is within 7 ms of the network floor.

### Outstanding

- HTTP interface returning measured features (weeks 2-3)
- On-chain storage contract (weeks 4-5)
- Lender validation (weeks 6-7)
- Base Ecosystem Fund application (week 8)

## Open questions

1. How many liquidation events exist on Moonwell Base over a usable label
   period? This determines whether PD and LGD are feasible at all, and it
   should be answered before any commitment is made to a lender.
2. What is the scoreable universe - wallets with an open position, not
   merely wallets that borrowed recently? A nine-borrower sample over eleven
   hours on one market is too thin to size a pilot.
3. What re-scoring cadence does a lender actually need? On demand, per
   block, or on threshold crossing? This determines the cost model, and free
   RPC tiers price by compute units per month rather than by requests per
   second.
4. If the scoring key is compromised, setScorer is callable only by the
   current scorer. An upgrade path should be designed before deployment
   rather than after.

## Constraints

- Interpretability is not optional. A credit decision must be explicable to
  the borrower it affects (CFPB Circular 2022-03), and the EU AI Act
  classifies creditworthiness assessment of natural persons as high-risk.
- Wallet-level scoring is not Sybil-proof and cannot be made so. Mitigations
  raise cost; they do not eliminate the exposure.
- Every claim in public-facing material must correspond to something
  measured. Literature benchmarks are labelled as such.