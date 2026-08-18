# SCORE — Regulatory Posture and Compliance Notes

> **This document is not legal advice.** It records the design decisions that
> shape SCORE's regulatory exposure and the reasoning behind them, so that the
> posture is explicit, reviewable, and stable as the codebase grows. Its
> conclusions are informed inferences from statute, regulation, and agency
> guidance — not a regulatory ruling and not a substitute for a reasoned
> opinion from qualified counsel. Obtaining that opinion is itself a required
> step (see "Open items").
>
> Last reviewed: 2026-08-17

## What SCORE is, in regulatory terms

SCORE is a **read-only, non-custodial on-chain analytics tool**. It reads
wallet positions from lending protocols on Base using `eth_call` — queries
that create no transaction, take no custody, move no value, and require no
signature — and computes solvency and credit-risk features from what it reads.

The following are true by design, and the design is what keeps them true:

- SCORE **takes no custody** of any asset, at any time.
- SCORE **transmits no value** and never accepts value from one party for
  transmission to another.
- SCORE **facilitates no transactions**. It does not lend, route, relay,
  swap, or settle.
- SCORE **holds no signing key** and initiates no state-changing call.
- SCORE **scores wallet addresses, not identified persons**. It collects,
  requests, and stores no real-world identity.

Each of these maps to a specific element of the regulatory tests below. They
are not incidental properties; they are the compliance posture.

## Why this posture keeps SCORE outside money-transmitter and VASP scope

### US — Bank Secrecy Act / FinCEN

A "money transmitter" under 31 CFR 1010.100(ff)(5) is a person who **accepts**
currency, funds, or value that substitutes for currency from one person and
**transmits** it to another location or person. Acceptance and transmission of
value is the threshold element. SCORE accepts nothing and transmits nothing,
so it does not reach that threshold.

FinCEN's 2019 interpretive guidance (FIN-2019-G001) states that a developer or
seller of a software application "may be exempt from BSA obligations associated
with creating or selling the application" unless it also uses the application
to engage as a business in accepting and transmitting value. SCORE is a
read-only analytics application that never accepts or transmits value. The
statutory exemption at 31 CFR 1010.100(ff)(5)(ii)(A) — for a person who only
provides "delivery, communication, or network access services" — points the
same way, though SCORE does not need to rely on the exemption because it does
not meet the definition in the first place.

Because no identified person opens an account or receives services, there is
no "customer" for Customer Identification Program purposes (31 CFR 1020.220 /
1022.210), and no CIP/KYC obligation attaches.

### The control test

Both FinCEN guidance and Treasury's 2023 DeFi risk assessment frame BSA
coverage around **control** over customer value. The Fifth Circuit's reasoning
in *Van Loon v. Department of the Treasury* (No. 23-50669, Nov. 26, 2024)
turned on the same axis: control over the thing in question. SCORE reads state
but cannot move, freeze, or direct any asset. It has no control, and therefore
no money-transmission nexus.

### EU — MiCA / AMLR

MiCA (Reg (EU) 2023/1114) enumerates the crypto-asset services that require
authorization — custody, exchange, transfer, execution, placing, advice,
portfolio management, and the like. Read-only analytics and credit scoring is
not among them, so SCORE is not a Crypto-Asset Service Provider. The Transfer
of Funds Regulation Travel Rule (Reg (EU) 2023/1113) and the AMLR
(Reg (EU) 2024/1624) attach to CASPs and other obliged entities; a read-only
analytics provider that is not a CASP is not, by itself, an obliged entity.

### FATF

FATF's five VASP activities are exchange, transfer, safekeeping/administration,
and participation in an issuer's offer/sale of a virtual asset. SCORE performs
none of them, and exercises no "control or sufficient influence" over any
asset or protocol under FATF's October 2021 owner/operator test. It is not a
VASP.

### The analytics analogy

SCORE is properly analogized to blockchain-analytics firms — Chainalysis,
Elliptic, TRM Labs — which read on-chain data and sell wallet risk scores and
screening to regulated firms **without** being money transmitters or VASPs.
They are software/analytics vendors. The distinction to preserve is exactly the
one those firms preserve: they inform others' risk and compliance decisions;
they never take custody or move funds. SCORE sits in the same category.

## The one binding obligation: OFAC sanctions

Non-money-transmitter status does **not** remove sanctions obligations. OFAC
sanctions apply to all US persons on a strict-liability basis, independent of
MSB or VASP status, and pseudonymity is not a defense — OFAC has attributed
specific crypto wallet addresses to designated persons on the SDN list since
2018.

SCORE transacts nothing, so it cannot "deal in" blocked property in the
ordinary transactional sense. But because it reads and scores wallet addresses,
its posture is to screen the addresses it reads and reports against OFAC's SDN
list and to handle matches appropriately. This is implemented as a dedicated
screening step (see `docs/OFAC_SCREENING.md` once that module lands).

Two properties of any screening implementation are treated as requirements
rather than niceties:

1. **The SDN list must be current.** The list changes continuously. A frozen,
   hardcoded snapshot is worse than no screening, because it presents the
   appearance of compliance while silently going stale. Screening fetches the
   published list (or uses a screening provider) and refreshes it.
2. **Screening is necessary, not sufficient.** Sanctions compliance is a legal
   obligation broader than any address match. The module reduces one specific
   risk; it does not discharge the obligation in full.

## What is NOT yet triggered — and what would trigger it

SCORE scores pseudonymous wallets and makes no credit decision about any
identified person. Two significant regimes are therefore dormant, and it is
worth being explicit about the line, because crossing it is a product decision
that should be made deliberately, not stumbled into.

### Consumer-finance law (US) — dormant

The Fair Credit Reporting Act (15 USC 1681) governs "consumer reporting
agencies" assembling information on identified "consumers." The Equal Credit
Opportunity Act (15 USC 1691) and Regulation B (12 CFR 1002) govern
"creditors" deciding on "applicants." A wallet address is neither a consumer
nor an applicant, and SCORE is not a creditor. Both regimes are dormant while
SCORE scores addresses.

They activate if SCORE's scores are used to make credit decisions about
**identified natural persons**. At that point SCORE could become a consumer
reporting agency, its lender-users would owe adverse-action duties, and CFPB
Circular 2022-03 would require that the model produce specific, accurate
principal reasons for an adverse decision — model explainability becomes a
legal requirement, not only a design preference.

### AI Act (EU) — dormant

Annex III, point 5(b) of the EU AI Act (Reg (EU) 2024/1689) classifies systems
that "evaluate the creditworthiness of natural persons or establish their
credit score" as high-risk. This covers **natural persons**, not businesses or
pseudonymous wallets. A wallet-only or business-counterparty risk model is
outside 5(b). It activates if SCORE produces an individual consumer
creditworthiness determination for EU natural persons.

## Scope-changing triggers (design-review gates)

The following features change SCORE's regulatory category. None may ship
without fresh legal review **before** implementation. This list is the
standing gate; treat any item on it as a stop-and-review, not a
proceed-with-caution.

| Feature | Risk it introduces |
|---|---|
| Identity linkage, KYC, or identity attestation | Obliged-entity status (US and EU); potential consumer-reporting-agency status |
| Scores used to decide credit for identified natural persons | FCRA/ECOA (US); AI Act Annex III high-risk (EU); adverse-action and explainability duties |
| Any custody, signing, routing, or fee taken inside a value flow | Money-transmitter / VASP status |
| Serving EU natural persons, or scores driving decisions about them | AI Act; possibly GDPR automated-decision rules |

On Sybil resistance specifically: if identity signal is ever needed to resist
Sybil attacks, the privacy-preserving path — a zero-knowledge "unique human"
proof that returns only a boolean and stores no personal data — keeps SCORE far
from obliged-entity and consumer-reporting status. Collecting or verifying
government-identity documents does the opposite. The mechanism chosen is a
compliance decision, not only an engineering one.

## Open items

These are required and not yet done. They are recorded here so the gap is
visible rather than assumed closed.

- **Reasoned legal opinion.** Obtain a written opinion from qualified US
  (BSA/OFAC) and EU (MiCA/AMLR) counsel confirming non-MSB, non-CASP status
  for the read-only design. This document briefs that review; it does not
  substitute for it. This is standard diligence for a Coinbase-ecosystem
  application and should be treated as a precondition to any public launch.
- **OFAC screening module.** Build the live-SDN screening step described above.
- **Sanctioned-jurisdiction access policy.** Decide and document a policy
  excluding sanctioned jurisdictions and persons from paid access.
- **Monitoring.** Track developments that would change the posture: enactment
  of a blockchain developer safe harbor, any FinCEN DeFi rulemaking finalizing
  coverage of "DeFi services," EU guidance extending CASP or obliged-entity
  status to analytics, and the outcome of the pending Tornado Cash developer
  proceedings.

## Status legend for the claims above

- **Settled regulation:** the money-transmitter definition (31 CFR
  1010.100(ff)); FCRA/ECOA/Regulation B as statutes and rules.
- **Non-binding agency guidance:** FIN-2013-G001; FIN-2019-G001; Treasury's
  2023 DeFi risk assessment; FATF guidance. Informative, not law.
- **Enacted but phasing in:** the AI Act creditworthiness classification.
- **Genuinely unaddressed:** no US or EU regulator has squarely addressed a
  read-only, non-custodial on-chain credit-scoring tool that scores
  pseudonymous wallets. The conclusion that SCORE sits outside
  money-transmitter, VASP, and CIP scope is a strong and well-supported
  inference from the control and acceptance-and-transmission tests and the
  analytics-firm analogy — it is not a point-blank regulatory holding, and this
  document does not represent it as one.
