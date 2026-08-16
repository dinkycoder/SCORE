\newpage

# Verification notes

> **Internal document. Remove before publication.**
>
> Every factual claim in the manuscript is recorded here in one of three
> states. A claim moves to CLOSED only when a primary source or an
> independent derivation has confirmed it. Plausibility does not close an
> item.
>
> Last reviewed: 2026-08-16 (rev 2)

## Closed

**Moonwell Comptroller address on Base.**
`0xfBb21d0380beE3312B33c4353c8936a0F13EF26C`. Confirmed 2026-08-15 against
docs.moonwell.fi/moonwell/protocol-information/contracts and against live
calls returning valid data for nine wallets.
*Note on provenance: an earlier draft carried a fabricated address in which
31 of 40 hexadecimal characters were correct. It was supplied from memory
and not checked. This episode is recounted in Chapter 2 §2.9.*

**USD scaling of Comptroller values.** Values are scaled by 1e18. Confirmed
2026-08-15 by independent derivation: liquidity computed from raw token
balances, oracle prices, and collateral factors agreed with the
Comptroller's own reported figure to a ratio of 1.000000 on wallet
`0xAA503ae37ba4A6FCC2fD6CC3F3Dc776Ab11B7b67`.

**Moonwell has no Base testnet deployment.** Confirmed 2026-08-15 against
the protocol's contracts documentation, which lists Base, Ethereum, OP
Mainnet, Moonbeam, and Moonriver, and no test network. Chapter 1 §1.5
corrected accordingly.

**Compound V2 `getAccountLiquidity` semantics.** At most one of liquidity
or shortfall is non-zero. Confirmed against Compound's own documentation and
consistent with observed behaviour across all wallets queried.

**Latency figures.** 1683 ms p95 before batching, 173 ms p95 after; 149 ms
for a single round trip. Measured locally 2026-08-15 across ten samples via
`tests/test_latency.py`. Machine-specific and provider-specific; should be
described as measured rather than as characteristic.

**Moonwell liquidation volume (feasibility of hurdle model).** Confirmed
2026-08-16 via DefiLlama, which reports Moonwell liquidation fees by quarter
(millions per quarter across 2024-2026). A liquidation fee is a share of each
liquidated position, so this establishes thousands of liquidation events,
far above the reference paper's 139-wallet severity sample. The modelled
stages are feasible on banked history; this closes open question 1 of the
prior Phase 0 draft.

**Moonwell oracle incidents.** PREVIOUSLY "not applicable" - now CONFIRMED.
DefiLlama records two: 2025-11-04, $1M, spot price manipulation (Base and
Optimism); and 2026-02-15, $1.78M, oracle misconfiguration (Base). Chapter 1
and these notes previously stated no incident had been confirmed. Two are now
confirmed from a primary aggregator. The manuscript should present these as
fact. They bear directly on SCORE, which inherits oracle manipulability.

**Moonwell TVL trajectory.** Confirmed 2026-08-16 via DefiLlama chart: peak
~$374M mid-2026, declined to ~$60M currently (~84% drawdown, ongoing), active
loans ~$31M. An earlier verbal figure of "8.7% over 30 days" measured only
the flattest recent segment and understated the full decline. The contraction
is real and is addressed in PHASE_0.md under protocol strategy.

**Morpho and Aave TVL trajectories (protocol-strategy basis).** Confirmed
2026-08-16 via DefiLlama charts. Morpho: near-monotonic growth to ~$8B, at or
near all-time high, growing. Aave: peaked ~$45B late 2025, declined to
~$13-15B, contracting. An earlier claim that "both are growing" was wrong on
Aave and is corrected: only Morpho is growing.

## Open

**Multicall3 address.** `0xcA11bde05977b3631167028862bE2a173976CA11` is
documented as a deterministic CREATE2 deployment identical across EVM
chains, and calls against it succeed on Base. The address has not been
independently confirmed against Basescan, and the deterministic-deployment
claim rests on secondary sources rather than on the deployer's own record.
Confirm before print.

**Aramonte et al. (2022), BIS Bulletin.** Cited in the Preface. Bulletin
number and exact publication date not confirmed. Verify on bis.org.

**Chiu et al. (2023), Bank of Canada SWP 2023-14.** Research returned
authors Chiu, Ozdenoren, Yuan & Zhang. The Achutha et al. reference list
gives a different author set for what appears to be the same paper. One of
the two is wrong; determine which before citing.

**Maple / Orthogonal figures.** $36 million across eight loans, roughly 30
percent of active loans, December 2022. Cited in the Preface from secondary
reporting. Confirm against Maple's own statement.

**Base TVL and activity figures.** $11.86 billion TVL; 12.89 million daily
transactions; 382,500 active addresses. Cited in Chapter 1 from secondary
sources reporting L2BEAT and CoinBureau data. Replace with direct L2BEAT
citation and a fixed access date. These figures move; the manuscript
presents them as a dated snapshot, which should be preserved.

**Moonwell close factor and liquidation incentive.** Chapter 1 §1.3 states
these generically, with fifty percent given as typical. The actual
governance-set parameters for Moonwell on Base have not been read.

**Palaiokrassas et al. (2024) performance figures.** AUC values attributed
to this paper during research came from a secondary citing source, not the
primary text. Do not cite the figures until the primary PDF is checked. The
paper itself is peer-reviewed (IEEE ICBC 2024) and safe to cite for its
approach.

**CFPB Circular 2022-03 Federal Register citation.** 87 Fed. Reg. 35864.
Confirm.

**EU AI Act Annex III applicability date.** High-risk obligations were
originally slated for 2 August 2026 and reportedly deferred by subsequent
amendment. The manuscript avoids stating a date. Verify current status on
EUR-Lex before any date is added.

**Armstrong on on-chain credit.** The claim that Coinbase leadership has
publicly framed on-chain credit scoring as an opportunity is not confirmed
in available reporting of the July 2026 podcast appearance. Cite the primary
recording with a timestamp, or omit.


**eth_getLogs free-tier cap (infrastructure fact, not a manuscript claim).**
Confirmed 2026-08-16 by direct probe: Alchemy free tier rejects eth_getLogs
above ~10 blocks per request with a -32600 error naming the plan limit. This
blocks bulk historical extraction and is recorded in PHASE_0.md. Noted here so
the constraint is not rediscovered.

## Not applicable

*(The prior "Moonwell oracle incidents - none located" entry has moved to
Closed: two incidents are now confirmed. See above.)*
