# SCORE — Counsel Briefing Memorandum

> **Purpose.** This memorandum is prepared to brief qualified regulatory
> counsel efficiently. It states what SCORE is, what it is not, the specific
> legal questions on which an opinion is sought, and the analysis already
> performed, so that counsel can confirm, correct, or refine a position rather
> than build one from nothing.
>
> **This document is not itself legal advice** and was not prepared by a
> lawyer. It is a client-side briefing. Its own analysis should be treated as
> a hypothesis for counsel to test.
>
> Prepared: 2026-08-17

---

## 1. What we are asking counsel to do

We seek a reasoned written opinion on three questions:

1. **US status.** Whether SCORE, as described in Section 2, is a "money
   transmitter" or "money services business" under the Bank Secrecy Act and
   FinCEN regulations, and whether it carries any independent registration,
   KYC, or reporting obligation.

2. **EU status.** Whether SCORE is a "crypto-asset service provider" under
   MiCA or an "obliged entity" under the EU AML regime (AMLR/AMLD6, TFR).

3. **Boundary conditions.** The specific product changes that would alter
   either answer — i.e., where the lines are — so that we can build a
   design-review gate around them.

A secondary request: confirmation that our OFAC sanctions-screening posture
(Section 5) is appropriate for a read-only tool, and identification of any
sanctions obligation we have not accounted for.

We are **not** asking counsel to opine on the soundness of the credit model,
the business, or matters outside regulatory law.

---

## 2. What SCORE is (the operative facts)

SCORE is a real-time, read-only, on-chain credit/solvency scoring system for
decentralized lending protocols on Base (an Ethereum Layer 2 operated by
Coinbase).

The facts material to the legal analysis, each of which is a design property
we can commit to in writing:

- **Read-only.** SCORE reads blockchain state using `eth_call` — queries that
  create no transaction, require no signature, consume no gas, and change no
  state.
- **Non-custodial.** SCORE never holds, controls, or has the ability to move,
  freeze, or direct any user asset, at any time.
- **No transmission of value.** SCORE never accepts value from one party for
  transmission to another. It transmits nothing.
- **No transaction facilitation.** SCORE does not lend, route, relay, swap,
  match, or settle. It initiates no state-changing call and holds no signing
  key.
- **Pseudonymous inputs.** SCORE scores wallet addresses. It does not collect,
  request, verify, or store any real-world identity, and it does not link
  wallets to identified natural persons.
- **Output.** SCORE produces solvency features and (on the roadmap) credit-risk
  scores, delivered as information to the parties who query it — anticipated to
  be lending protocols and lenders assessing borrower-wallet risk.

What SCORE charges for, if and when it charges, is access to information /
analytics. Any fee is for the analytics service and is not taken from, or
contingent on, any flow of user funds.

---

## 3. The US analysis we have performed (for counsel to test)

**Money-transmitter definition.** 31 CFR 1010.100(ff)(5) defines a money
transmitter by the acceptance of value from one person and its transmission to
another. Acceptance-and-transmission is the threshold element. SCORE accepts
and transmits nothing, so on our reading it does not meet the definition.

**FinCEN 2019 guidance (FIN-2019-G001).** The guidance states that a developer
or seller of a software application "may be exempt from BSA obligations
associated with creating or selling the application" unless it also uses the
application to engage as a business in accepting and transmitting value. SCORE
is a read-only analytics application that never accepts or transmits value. The
"anonymizing software provider" vs. "anonymizing service provider" distinction
in the same guidance also appears to place a passive software/analytics tool on
the non-transmitter side.

**The exemption.** 31 CFR 1010.100(ff)(5)(ii)(A) exempts a person who only
provides "delivery, communication, or network access services." We do not
believe SCORE needs to rely on this, because it does not meet the threshold
definition, but it appears to be an alternative ground.

**The control test.** FinCEN guidance and Treasury's 2023 DeFi risk assessment
frame BSA coverage around control over customer value; *Van Loon v. Department
of the Treasury* (5th Cir., No. 23-50669, Nov. 26, 2024) turned on control over
the asset in question. SCORE has no control over any asset.

**CIP.** Without an identified person opening an account, we read 31 CFR
1020.220 / 1022.210 as imposing no Customer Identification Program duty.

**Our tentative conclusion:** SCORE is not a money transmitter or MSB and has
no independent BSA registration/KYC/reporting obligation in its read-only,
pseudonymous form. **We ask counsel to confirm or correct this.**

**The analogy we are relying on:** blockchain-analytics firms (Chainalysis,
Elliptic, TRM Labs) that read on-chain data and sell risk scores without being
money transmitters or VASPs. We ask counsel whether this analogy holds for
SCORE and whether there is contrary authority.

---

## 4. The EU analysis we have performed (for counsel to test)

**MiCA (Reg (EU) 2023/1114).** The enumerated crypto-asset services (custody,
exchange, transfer, execution, placing, advice, portfolio management, etc.) do
not, on our reading, include read-only analytics or credit scoring. We read
SCORE as not a CASP.

**AML regime (AMLR Reg (EU) 2024/1624; AMLD6 Dir (EU) 2024/1640; TFR Reg (EU)
2023/1113).** These attach to CASPs and other obliged entities. A read-only
analytics provider that is not a CASP appears not to be an obliged entity.

**Our tentative conclusion:** SCORE is not a CASP or an obliged entity in its
current form. **We ask counsel to confirm or correct this**, and to flag any
member-state-level variation that matters.

---

## 5. Sanctions posture (for counsel to review)

We treat OFAC sanctions as a binding obligation independent of MSB status,
applicable on a strict-liability basis to US persons. Our implementation:

- We screen wallet addresses SCORE reads/reports against the OFAC SDN list
  (crypto-address entries).
- Screening fails closed: if the list cannot be freshly verified, the system
  returns an error rather than a result.
- We screen against a maintained, nightly-updated derivation of OFAC's
  `sdn_advanced.xml` (the 0xB10C project), with a documented plan to move to
  direct OFAC parsing or a commercial screening provider for production.
- A sanctioned address is flagged, not hidden; we do not provide any bespoke
  service to a sanctioned person.

**We ask counsel:** is this posture appropriate for a read-only tool that
transacts nothing? Is there any sanctions obligation (e.g., around merely
providing analytics output referencing a sanctioned address) we have not
accounted for? Does scoring a sanctioned wallet for risk purposes create any
exposure?

---

## 6. Boundary conditions we have identified (for counsel to refine)

We have built a design-review gate around the following changes, which we
believe would alter the analysis. We ask counsel to confirm these are the right
triggers and to identify any we have missed:

| Change | Regime we believe it implicates |
|---|---|
| Linking wallets to identified natural persons; performing KYC or identity attestation | US obliged-entity / consumer-reporting status; EU obliged-entity status |
| Scores used to make credit decisions about identified natural persons | FCRA (15 USC 1681) / ECOA (15 USC 1691) / Reg B; CFPB Circular 2022-03 adverse-action; EU AI Act Annex III 5(b) high-risk |
| Taking custody, holding a signing key, routing/relaying, or taking a fee inside a value flow | Money-transmitter / VASP status (US and EU) |
| Serving EU natural persons, or scores driving decisions about them | EU AI Act; possibly GDPR automated-decision rules (cf. the SCHUFA line of CJEU authority) |

On Sybil resistance specifically: if we introduce an identity signal, we intend
to use a privacy-preserving proof-of-personhood that returns only a "unique
human" boolean and stores no personal data, rather than collecting identity
documents. **We ask counsel whether that design choice keeps SCORE outside
obliged-entity and consumer-reporting status**, and what the minimum-viable
identity signal is that would NOT cross the line.

---

## 7. Documents we can provide

- `COMPLIANCE.md` — our full regulatory posture, with citations, mapping each
  design property to the test it addresses.
- `docs/OFAC_SCREENING.md` — the screening implementation and its documented
  limits.
- The source code, which is read-only by construction (no signing key, no
  custody function exists in the codebase).
- A longer research memorandum with primary-source citations (statutes,
  regulations, FinCEN guidance by document number, Treasury and FATF materials,
  MiCA/AMLR/TFR by regulation number, and relevant case law including *Van Loon*
  and the *Storm* proceedings).

---

## 8. Current regulatory climate (context, not argument)

As of 2026, the US posture is comparatively crypto-permissive: an executive
order of January 23, 2025 reoriented federal policy toward supporting digital
assets; the IRS "DeFi broker" reporting rule was repealed in April 2025; and a
blockchain developer safe-harbor bill (the Blockchain Regulatory Certainty Act)
has been reintroduced though not enacted. We note this as context. We are not
relying on it: our position is that SCORE is outside money-transmitter scope on
the settled definition, regardless of climate. We ask counsel to advise on a
basis that does not depend on the current administration's enforcement posture.

---

## 9. The single most important caveat

No US or EU regulator has, to our knowledge, squarely addressed a read-only,
non-custodial, on-chain credit-scoring tool that scores pseudonymous wallet
addresses. Our conclusion that SCORE sits outside money-transmitter, VASP, and
CIP scope is a reasoned inference from the acceptance-and-transmission and
control tests and the analytics-firm analogy — not a point-blank holding. We
are seeking counsel precisely because the question is novel, and we would rather
have a documented professional opinion than proceed on our own reading, however
carefully assembled.
