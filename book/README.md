# Reading the Chain - manuscript

Book manuscript for the SCORE project. One file per chapter; chapters are
written after each build stage ships.

## Files

- 00-title.md ................ Title page
- 00-preface.md .............. Preface: origin, thesis, structure
- 01-reading-the-chain.md .... Ch. 1: querying lending-protocol state on Base
- 02-verifying-the-arithmetic.md .... Ch. 2: reconstructing a wallet's position
- 03-a-second-protocol.md .... Ch. 3: Morpho Blue's isolated-market model
- 04-scoring-in-real-time.md . Ch. 4: the HTTP service and its claim boundary
- 99-verification-notes.md ... INTERNAL. Unconfirmed citations. Not for publication.

Chapters are numbered so they sort correctly. Add 05-, and so on as
stages complete.

## Pagination

Markdown has no pages. Each file begins with a \newpage directive, which
Pandoc converts to a real page break in PDF, DOCX, and EPUB output. Reading
the .md files directly on GitHub, the directive appears as literal text.
That is expected and harmless.

## Building

Requires Pandoc (pandoc.org). For PDF output, a LaTeX engine is also needed.

    pandoc 00-title.md 00-preface.md 01-*.md --toc --toc-depth=2 -o reading-the-chain.docx

The glob 01-*.md becomes 0*-*.md once there are more chapters. The
verification notes file is excluded from every build target on purpose.

## Citation style

APA 7. References are listed per chapter while chapters are drafted
independently. Consolidate into a single back-matter bibliography before
publication, at which point move to a .bib file and let Pandoc handle it
via --citeproc.

## Voice

Adapted from the author's dissertation register: formal, no contractions,
elevated diction, dense citation, authorities given lineage rather than bare
surnames. Canonical frameworks are re-run step by step in the new domain
rather than merely cited. First person is permitted where the beginner's
account requires it.

## Standing rules

- Every claim about the world gets a source; claims about the code do not.
- Contested or fast-moving figures get a range and a date, not a single number.
- Failed experiments stay in the text.
- Nothing moves from 99-verification-notes.md into a chapter until it has
  been checked against a primary source.
- Chapters correspond to completed build stages, but the stages are not
  fixed in advance. The preface's chapter map (added 2026-08-16) was
  written against the plan as it stood at the time; it describes the map's
  origin, not a ceiling on what the book may cover. When a stage occurs
  that the map did not anticipate — as happened 2026-08-23, when the
  Morpho reader was built to prove SCORE's method ports beyond
  Compound-family protocols, a piece of work the original plan did not
  contain — the map is revised to include it, in the position that serves
  the reader's learning best, and the revision is noted in the preface
  rather than pretended away. The book documents the project as built,
  not as originally scheduled.