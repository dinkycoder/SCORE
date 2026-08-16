\newpage

# Preface

## The paper that started this

In March 2026, Achutha M, Bhoomika R. Hegde, and Bhaskarjyoti Das of the Department of Computer Science and Engineering at PES University, Bengaluru, published in the *International Journal of Data Science and Analytics* a paper titled "Transaction graph-based predictive hurdle model for credit scoring in DeFi lending protocols" (Achutha et al., 2026). The title is forbidding. The finding is not.

Utilizing six years of transaction data from the Compound V2 lending protocol — 340,737 transactions across 37,332 unique wallets — the authors constructed a model that ranks borrowers according to their likelihood of liquidation. Of the one hundred wallets the model identified as riskiest, every one was liquidated during the observation period. That cohort constituted four-tenths of one percent of the wallets scored, and it concentrated realized risk at approximately fifty times the baseline liquidation rate (Achutha et al., 2026).

I did not understand the paper on first reading, nor on third. What was apparent, however, was the shape of the claim.

Fifty-fold concentration, derived entirely from public data, concerning borrowers whose identities are unknown and unknowable. If the riskiest half-percent of participants in a lending market can be identified using nothing but that market's own transaction record — absent a credit bureau, absent income verification, absent identity of any kind — then something that has held true throughout the history of credit has quietly ceased to hold.

This book is an attempt to determine what that something is, and to construct a working system upon it.

## What this book is, and for whom it is written

This book is written for readers who know nothing of the subject.

Precision on that point is warranted, because the claim of accessibility is made frequently in technical writing and honored infrequently. At the commencement of this project I could not have described the contents of a blockchain transaction. I did not know the meaning of *overcollateralized*. I had written no Solidity, had never queried a remote procedure call endpoint, and could not have defined *loss given default* had I been given two of the three words. I was not an expert who elected to write for beginners. I was a beginner who elected to document the process.

The structure follows from that circumstance. This book constitutes the documentation layer of a software project named SCORE — a real-time credit scoring system for lending protocols on Base, the Ethereum Layer 2 network operated by Coinbase. The project proceeds in stages. Each stage produces working software. Each chapter is composed after its corresponding stage is complete, and addresses what that stage required its author to learn.

That constraint performs genuine work. Every concept in this book is introduced at the moment it became load-bearing, and not before. Liquidation mechanics are not presented in the abstract; they are presented in Chapter 1, because Chapter 1 is where a wallet's liquidation risk had to be queried and the returned values proved unintelligible. Graph theory is not surveyed; it appears when the model requires it. The chapters are the residue of problems encountered.

The hazard of composing a book in this manner is evident: a person documenting an education is not an authority. Two measures mitigate that hazard. First, every claim about the world — as distinguished from claims about the software — is sourced, and sources are named in the text where the reader may examine them. Second, the seams remain visible. Where the literature disagrees with itself, the disagreement is reported. Where a figure is contested or fast-moving, a range and a date are supplied in place of a single number. Where an error was committed and subsequently corrected, the error remains in the account.

Upon completion, the reader should be capable of three things: reading a lending protocol's on-chain state and comprehending what is displayed; reasoning about credit risk in the vocabulary employed by a bank risk officer; and explaining to a sophisticated and skeptical audience why an on-chain credit score constitutes a business rather than an exercise.

## The oldest problem in finance

What renders credit difficult is not mathematics. It is that the borrower possesses information the lender does not.

George Akerlof (1970), whose work on this subject was later recognized by the Nobel Memorial Prize in Economic Sciences, formalized the difficulty in a paper concerning used automobiles. Where sellers know more about quality than buyers, the market may collapse: buyers price according to the average, superior sellers withdraw because the average price undervalues their goods, average quality consequently declines, buyers revise their pricing downward, and the spiral continues. Akerlof was explicit that credit markets constitute an instance of the same pathology, and he identified lending in developing economies as a case in point.

Joseph Stiglitz and Andrew Weiss (1981) advanced the argument to a conclusion that remains counterintuitive. In a market characterized by information asymmetry, lenders will not simply raise interest rates until supply meets demand. Elevating rates selects against the lender: safe borrowers exit first, being aware of their own risk and unwilling to pay a premium they do not merit, while risky borrowers remain. There exists, accordingly, an interest rate above which the lender's expected return declines. The lender halts at that rate and declines to lend to the remainder — not because those borrowers are unwilling to pay more, but because willingness to pay more is itself an adverse signal. This phenomenon is termed *credit rationing*, and its implication is that creditworthy borrowers are refused in equilibrium.

Douglas Diamond (1984) then supplied the explanation for institutions. Borrowers must be monitored, monitoring is costly, and it is wasteful for every individual lender to conduct that monitoring separately. Lenders therefore delegate the function to an intermediary — a bank — which performs it once on behalf of all. The bank exists because information is costly, and the bank's business is the production of information concerning borrowers.

Three papers, three Nobel laureates among their authors, and one shared conclusion: **credit is an information problem, and the institutions of credit are machines for producing information.**

The remainder follows. Credit bureaus exist to aggregate repayment histories. Statistical scoring exists to render those histories numerical, a lineage originating in David Durand's (1941) work for the National Bureau of Economic Research, which applied discriminant analysis to consumer installment lending, and proceeding through Edward Altman's (1968) Z-score for corporate bankruptcy to the consumer scoring methods reviewed by Hand and Henley (1997). Collateral requirements, covenants, and personal guarantees exist to align incentives where information is exhausted (Jensen & Meckling, 1976). The entire architecture constitutes scaffolding erected around a single deficiency: *the lender does not know who the borrower is.*

## What decentralized finance did instead

Decentralized finance did not resolve this problem. It circumvented it.

DeFi lending protocols permit any party to borrow without identity, credit assessment, or conversation. The resulting risk is managed by demanding collateral in excess of the loan — one might deposit $150 of ether to borrow $100 of a stablecoin — and by encoding an automatic rule within the contract: should collateral fall below a specified threshold, any party in the world may seize it and discharge the debt on the borrower's behalf, retaining a premium for the service. No judge, no collections call, no notice.

The arrangement functions. It is also, economically considered, a confession. Economists at the Bank for International Settlements titled their assessment of the sector "DeFi lending: intermediation without information?" (Aramonte et al., 2022), and the interrogative performs considerable diplomatic labor. A subsequent BIS study of Aave V2, among the largest such protocols, determined that borrowing was motivated predominantly by speculation rather than by the productive purposes credit ordinarily serves, and traced the sector's expansion from nothing to more than $50 billion in total value locked within a period of less than two years (Cornelli et al., 2024). A Bank of Canada working paper demonstrated that the rigidity of these automatic rules generates a price–liquidity feedback loop, producing multiple self-fulfilling equilibria in which an entire market may shift upon sentiment alone (Chiu et al., 2023).

The more consequential limitation, however, concerns what overcollateralization forecloses. A system that will extend credit only to parties already possessing more capital than they wish to borrow is not a credit system. It is a pawnbroker with superior uptime. It cannot capitalize an enterprise, cannot serve any party lacking existing capital, and cannot accomplish the function for which credit exists: the transfer of purchasing power to those who will employ it productively and repay it.

The magnitude of what is thereby foreclosed has been measured. The International Finance Corporation estimated an unmet financing need of **$5.2 trillion annually** among formal micro, small, and medium enterprises in developing economies — some 65 million businesses, constituting approximately 40 percent of that population (IFC, 2017). A subsequent re-estimation employing 2019 data across 119 emerging markets placed the formal MSME financing gap at **$5.7 trillion, approximately 19 percent of those economies' combined gross domestic product**, with an additional $2.1 trillion of informal-sector demand beyond it (SME Finance Forum, 2019). These are enterprises capable of servicing a loan and unable to obtain one. Stiglitz and Weiss described the mechanism in 1981; the IFC quantified it in dollars.

Attempts at uncollateralized on-chain lending have largely failed, and the failures instruct. In December 2022, Orthogonal Trading defaulted upon approximately **$36 million across eight loans** on Maple Finance — roughly 30 percent of that pool's active loans — following what Maple publicly characterized as material misrepresentations concerning its financial position, specifically its exposure to the collapsed exchange FTX (Maple Finance, 2022). The lesson is not that uncollateralized lending is impossible. The lesson is that uncollateralized lending constructed upon *self-reported* borrower information reproduces every failure mode of traditional credit while discarding traditional credit's legal enforcement. Trust absent verification does not constitute a business model.

## The gap this book addresses

The situation, stated plainly, is as follows.

Credit is an information problem. Traditional finance resolved it by constructing an identity infrastructure that required a century to build and continues to exclude billions of persons. Decentralized finance discarded the identity infrastructure and, possessing no information, substituted collateral — which functions, and which confines the entire sector to parties who do not require credit.

Decentralized finance discarded identity, however, while producing something traditional finance never possessed: **a complete, public, permanent, and machine-readable record of every borrower's conduct.**

Every loan. Every repayment. Every liquidation. Every position a wallet has ever held, timestamped, within an append-only ledger that any party may read without permission. A credit bureau expends considerable resources assembling a partial, lagging, and error-prone representation of a borrower's history. A blockchain supplies a complete and exact one, without charge, updated continuously.

The identity is absent. The conduct is not. And the wager underlying this entire undertaking — the wager the Achutha et al. (2026) paper tests and substantially wins — is that for purposes of predicting default, *conduct is the portion that matters.*

## Organization of the book

Chapters correspond to build stages.

**Chapter 1 — Reading the Chain.** The contents of a lending protocol's on-chain state, the method of querying it, and the meaning of the returned values. Constructs a working client that reads live wallet state from a lending market on Base.

**Chapter 2 — Verifying the Arithmetic.** The reconstruction of a wallet's full position, the decimal conventions governing it, and the method by which a numerical assumption is established rather than assumed. Includes an account of four defects, each of which passed its own tests.

**Chapter 3 — Scoring in Real Time.** The conversion of verified features into a service that responds within a second, and the boundary between what such a service measures and what it may claim.

**Chapters 4–5 — Trust on Chain.** Why a score residing upon a private server is worth less than one anchored to a public ledger, and the construction of the contract that anchors it.

**Chapters 6–7 — Contact With Reality.** The presentation of the score to actual lenders and the discovery of its deficiencies. This chapter is the one most likely to be painful.

**Chapter 8 — The Pitch.** The assembly of the foregoing into an argument a fund may evaluate, together with candor concerning what the argument does not yet support.

Three constraints obtain throughout. **Interpretability is not optional** — the Consumer Financial Protection Bureau has determined that lenders may not employ algorithms so complex that the specific reasons for a denial cannot be furnished to the borrower (CFPB, 2022), and the European Union's Artificial Intelligence Act classifies systems evaluating the creditworthiness of natural persons as high-risk (Regulation (EU) 2024/1689). **Pseudonymity constitutes a vulnerability and not merely a feature** — a single party may operate a thousand wallets, and John Douceur (2002) demonstrated that absent a central authority such conduct cannot be fully prevented. **The critics warrant engagement rather than dismissal** — legal scholars have argued that crypto-native credit scoring risks constructing a new opaque apparatus with fresh potential for predatory lending (Packin & Lev-Aretz, 2024). Each receives substantive treatment where it becomes pertinent, which is to say as a design constraint rather than as an appendix.

## A note on honesty

One further matter warrants statement before the technical material commences.

The Achutha et al. (2026) paper with which this preface opens is careful in a manner this book aspires to emulate. Its authors report a headline result of fifty-fold risk concentration, and then, within the same paper, disclose that their loss-severity model was trained upon 139 wallets; that their community-structure signal ranges from meaningfully positive to slightly negative depending upon parameters of their own selection; that their transaction graph is time-collapsed and may therefore omit short-horizon structural transitions; and that their price data derive from transaction-implied values rather than from a manipulation-resistant oracle, a limitation they name explicitly.

They published the figure *and* the grounds for doubting it. That is the character of sound work, and it is the standard this book attempts to satisfy — including in those chapters where the honest report is that a thing did not function.

Let us begin.

## References

Achutha, M., Hegde, B. R., & Das, B. (2026). Transaction graph-based predictive hurdle model for credit scoring in DeFi lending protocols. *International Journal of Data Science and Analytics, 22*, 124. https://doi.org/10.1007/s41060-026-01097-7

Akerlof, G. A. (1970). The market for "lemons": Quality uncertainty and the market mechanism. *The Quarterly Journal of Economics, 84*(3), 488–500. https://doi.org/10.2307/1879431

Altman, E. I. (1968). Financial ratios, discriminant analysis and the prediction of corporate bankruptcy. *The Journal of Finance, 23*(4), 589–609. https://doi.org/10.1111/j.1540-6261.1968.tb00843.x

Aramonte, S., Doerr, S., Huang, W., & Schrimpf, A. (2022). DeFi lending: Intermediation without information? *BIS Bulletin*. Bank for International Settlements.

Chiu, J., Ozdenoren, E., Yuan, K., & Zhang, S. (2023). *On the fragility of DeFi lending* (Staff Working Paper No. 2023-14). Bank of Canada.

Consumer Financial Protection Bureau. (2022). *Circular 2022-03: Adverse action notification requirements in connection with credit decisions based on complex algorithms.* 87 Fed. Reg. 35864.

Cornelli, G., Gambacorta, L., Garratt, R., & Reghezza, A. (2024). *Why DeFi lending? Evidence from Aave V2* (BIS Working Papers No. 1183). Bank for International Settlements.

Diamond, D. W. (1984). Financial intermediation and delegated monitoring. *The Review of Economic Studies, 51*(3), 393–414. https://doi.org/10.2307/2297430

Douceur, J. R. (2002). The Sybil attack. In P. Druschel, F. Kaashoek, & A. Rowstron (Eds.), *Peer-to-peer systems: IPTPS 2002* (Lecture Notes in Computer Science, Vol. 2429, pp. 251–260). Springer. https://doi.org/10.1007/3-540-45748-8_24

Durand, D. (1941). *Risk elements in consumer instalment financing.* National Bureau of Economic Research.

Hand, D. J., & Henley, W. E. (1997). Statistical classification methods in consumer credit scoring: A review. *Journal of the Royal Statistical Society: Series A, 160*(3), 523–541. https://doi.org/10.1111/j.1467-985X.1997.00078.x

International Finance Corporation. (2017). *MSME finance gap: Assessment of the shortfalls and opportunities in financing micro, small, and medium enterprises in emerging markets.* World Bank Group.

Jensen, M. C., & Meckling, W. H. (1976). Theory of the firm: Managerial behavior, agency costs and ownership structure. *Journal of Financial Economics, 3*(4), 305–360. https://doi.org/10.1016/0304-405X(76)90026-X

Maple Finance. (2022, December 5). *Update on Orthogonal Trading.* https://maple.finance

Packin, N. G., & Lev-Aretz, Y. (2024). Crypto-native credit score: Between financial inclusion and predatory lending. *Cardozo Law Review, 45*(3), 845.

Regulation (EU) 2024/1689 of the European Parliament and of the Council of 13 June 2024 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act), OJ L 2024/1689 (2024).

SME Finance Forum. (2019). *MSME finance gap database.* International Finance Corporation.

Stiglitz, J. E., & Weiss, A. (1981). Credit rationing in markets with imperfect information. *The American Economic Review, 71*(3), 393–410.
