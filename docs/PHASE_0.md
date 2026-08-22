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
drive it: solvency triage is deliverable now and defensible standing alone,
and label extraction is the longest pole in the work. The feasibility of the
modelled stages is addressed directly below.

## Feasibility of the hurdle model (resolved 2026-08-16)

Open question 1 of the previous draft asked whether Moonwell on Base carries
enough liquidation events to fit PD and LGD. The answer is yes.

DefiLlama reports Moonwell liquidation fees as a distinct revenue line by
quarter. A liquidation fee is a percentage of each liquidated position, so
the fee total is a direct proxy for liquidation volume. Recent quarters
(protocol-wide, ~95% Base):

| Quarter | Liquidation fees |
|---|---|
| Q4 2024 | $1.02M |
| Q1 2025 | $2.23M |
| Q2 2025 | $773K |
| Q3 2025 | $853K |
| Q4 2025 | $1.88M |
| Q1 2026 | $1.14M |
| Q2 2026 | $104K |

Millions of dollars in liquidation fees per quarter implies thousands of
liquidation events, but an implication is not a count - it assumes an
average liquidation size nobody had checked. **2026-08-22: counted
instead.** `scripts/count_liquidations.py` scanned actual `LiquidateBorrow`
events over a 3-day window (blocks 50,177,530-50,307,130) and found **66
events, 52 distinct liquidated wallets**, written to
`data/liquidations_3d.csv` (block, tx hash, market, liquidator, borrower,
amounts - independently checkable, not just a total). 18 of 12,961
10-block windows never succeeded even after 12 retries, so this is a
**measured lower bound**, not an exact count, over **3 days out of the
multi-year history the fee table above spans** - not a claim about the
full period.

Even at this floor, 52 distinct wallets in 3 days already exceeds a third
of the 139-wallet sample Achutha et al. trained their loss-severity stage
on. A linear scale-up (52 x 630/3 ~= 10,900 over the ~630 days the fee
table spans) is an extrapolation, not a measurement, and is stated as
one: real activity is not uniform across that period (see the contraction
below), but it corroborates the fee-revenue inference's direction and
supersedes it as evidence - the fee table is now context for why the
count is plausible, not the basis for the "yes."

Two caveats attach. First, the label stock is historical: most of it was
generated in 2024 through early 2026, and the Q2 2026 collapse to $104K
reflects the protocol contraction described below. The training data is
banked; the live label stream is thinning. Second, extracting these labels
at scale is blocked on infrastructure (see the eth_getLogs constraint
below) - the 3-day sample above took ~78 minutes at a measured, degrading
~2.8-4.4 windows/s on the free tier, which is why it's 3 days and not the
full history.

## Protocol strategy: learn on one, demonstrate on another

Moonwell's total value locked peaked near $374M in mid-2026 and has since
fallen to roughly $60M, an ~84% drawdown that is still in progress at the
time of writing. Active loans stand near $31M. This is a functioning market
but a contracting one, and it is past its peak.

The contraction does not invalidate SCORE. Credit scoring learns from
liquidation history, that history is banked, and the method is independent
of where TVL sits today. What the contraction affects is the choice of
demonstration venue: scoring borrowers on a protocol that has lost most of
its TVL is a weak frame for a lender or a funding pitch, regardless of the
method's soundness.

The resolution is the property already latent in `config.py`: the protocol
is a configuration, not an architectural commitment. The plan is therefore
to separate the protocol SCORE *learns the method on* from the protocol it
*demonstrates on*.

**Learn on Moonwell.** It is a literal Compound V2 fork, which is why the
existing client works against it and why it matches the reference paper's
own dataset. Its banked liquidation history supports the PD/LGD work at low
integration cost. Its contraction is irrelevant to this purpose.

**Demonstrate on Morpho.** Morpho is the largest lending protocol on Base
and, unlike Moonwell and Aave, is growing rather than contracting (near
all-time-high TVL at the time of writing). It is therefore the venue a
lender or the Base Ecosystem Fund actually wants to see SCORE run against.
The cost is real and should not be understated: Morpho uses an
isolated-market architecture rather than Compound's shared-pool Comptroller
model, so there is no account-level getAccountLiquidity spanning positions.
`BaseRPCClient` would be rewritten against a different accounting model, not
adapted, and the verification work (scaling derivation, independent-liquidity
check) redone. This is the single largest piece of Phase 1 engineering.

**Aave is a contingent third, not a priority.** Aave V3 on Base is larger
than Moonwell and architecturally more familiar than Morpho (pooled
liquidity, a health factor, an account-level view). But Aave is itself
contracting from a late-2025 peak near $45B down to the $13-15B range, so it
is neither the cheapest teacher (Moonwell fills that role) nor the strongest
shop window (Morpho, growing, fills that). Aave becomes relevant only if a
specific lender uses it.

The throughline for the pitch: portability is the product. "SCORE runs on
any Compound-family protocol and extends to Morpho's isolated-market model"
demonstrates that the method generalises across lending architectures, which
is a stronger claim than anything tied to a single protocol. Morpho's growth
is what makes the demonstration land; its architectural distance from
Compound is what makes the demonstration mean something.

## Confirmed protocol risk: oracle incidents

DefiLlama records two security incidents on Moonwell, both oracle attacks,
both recent:

- **2025-11-04** — $1M, spot price manipulation, Base and Optimism.
- **2026-02-15** — $1.78M, oracle misconfiguration, Base.

These are directly relevant to SCORE. The system computes features from the
protocol's own oracle prices, so a score inherits the oracle's
manipulability, which is the same limitation Achutha et al. name in their own
pipeline. The Comptroller's oracle-override admin function was flagged in
Chapter 1 as a design-level risk surface; these incidents are the realised
form of that risk. Both belong in the book as fact rather than speculation.

## Corrections to the original plan

Assumptions in the first draft that did not survive contact with the
protocol:

**Base Sepolia.** Moonwell has no Base testnet deployment. Reads run against
mainnet, which is safe because eth_call requires no transaction, gas, or
signature. Contract deployment in weeks 4-5 may still target Sepolia.

**Latency budget.** The public RPC endpoint cannot serve the call volume a
score requires; a dedicated endpoint is a prerequisite, not an optimisation.

## Infrastructure constraint: eth_getLogs on the free tier

Alchemy's free tier caps eth_getLogs at EXACTLY 10 blocks per request -
confirmed 2026-08-22 via `scripts/probe_range.py`, which reads the number
directly out of Alchemy's own rejection message rather than assuming it.

Measured the same day via `scripts/count_liquidations.py`: sustained
throughput at that cap is ~4.4 windows/s at the start of a run, degrading
to ~2.8/s over a sustained ~78-minute run, and the ceiling held regardless
of worker count (2, 4, and 5 concurrent workers all converged to
approximately the same rate) - it is an account-wide throttle, not
something more concurrency fixes. At the low end of that range, a 90-day
window would take roughly 24-34 hours of wall time; a full year, 4-10
days. Both are a live background job away, not a blocker, but neither
fits inside a single working session - this is why the dataset above is 3
days, not 90.

This does not affect the live scoring path, which uses eth_call and
Multicall3, both of which work within free-tier limits. It affects only
bulk historical event extraction, which the PD/LGD stages require.

The resolution for Phase 1 is one of: a paid RPC tier with a higher
eth_getLogs range, or a subgraph/indexer that has already indexed the
events. Locating and validating a Base-specific liquidation subgraph is
itself a task; The Graph's hosted service is deprecated and the network now
requires API keys. This is a named Phase 1 cost, not a solved problem.

## Status

### Complete

- Base RPC client reading full wallet positions across all Moonwell markets
- All reads batched through Multicall3: one network round trip per wallet
- Point-in-time solvency features, including capacity utilisation,
  headroom / debt_rise_to_liquidation (the two directions of "how far
  prices must move to liquidate," kept as separate fields since they are
  different numbers), and volatility mismatch
- Position arithmetic verified against the Comptroller's own on-chain
  computation to a ratio of 1.000000
- 34 tests, including a live latency gate and a live correctness gate
- HTTP interface returning measured features (/position, /capabilities,
  /health), with no unearned model claims

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

- Test coverage for the HTTP interface (weeks 2-3)
- On-chain storage contract (weeks 4-5)
- Historical liquidation extraction, pending the infrastructure resolution
  above (Phase 1)
- Morpho reader for the demonstration venue (Phase 1)
- Lender validation (weeks 6-7)
- Base Ecosystem Fund application (week 8)

## Open questions

1. What is the scoreable universe of wallets holding open positions on
   Moonwell, as distinct from wallets that borrowed recently?
2. What re-scoring cadence do lenders require, and what does that cost
   against RPC compute-unit pricing?
3. `CreditScorer.sol` has no `setScorer` function - `scorer` is set once in
   the constructor and cannot be changed after deployment. That means a
   compromised or lost scorer key has no recovery path today: there is no
   privileged function to lock down, but also no way to rotate the key
   without redeploying the contract. Before this contract holds anything
   consequential, decide deliberately between adding a guarded rotation
   function (which introduces the privileged-function risk the previous
   version of this question assumed already existed) and keeping it
   immutable and accepting redeployment as the only recovery path.

## Constraints

- Interpretability is not optional. A credit decision must be explicable to
  the borrower it affects (CFPB Circular 2022-03), and the EU AI Act
  classifies creditworthiness assessment of natural persons as high-risk.
- Wallet-level scoring is not Sybil-proof and cannot be made so. Mitigations
  raise cost; they do not eliminate the exposure.
- A score computed from oracle prices inherits the oracle's manipulability.
  Two oracle incidents on Moonwell are documented above.
- Every claim in public-facing material must correspond to something
  measured. Literature benchmarks are labelled as such.
