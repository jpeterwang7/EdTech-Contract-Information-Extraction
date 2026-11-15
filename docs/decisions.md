# Decision log

What was decided at each step, why, and what happened. IDs like R7 are referred to in the code. The failures behind
these decisions are in [what_failed.md](what_failed.md).

## At a glance (Nov 2, 2026)

| Step | Decision | Result so far |
|---|---|---|
| Read pages | PDF's own text where it exists; OCR on scans | 0.37% of letters wrong on scans (old pipeline: 8.8%) |
| Pricing tables | Read by column position; numbers taken as printed | 88 product rows found |
| Order-form fields | Find each label on the page, take the value beside it; running text for header fields it misses | 98 of 99 values right |
| Clean text | Remove page clutter, join lines into whole paragraphs | Cut-off sentences: 2,119 → 10 |
| Privacy passages | Term list, semantic similarity and Llama vote on each block; a person checks where they disagree | All core text found; a person reads 8.6% of the words; matches a person's yes or no on 484 of 487 blocks (tuning files) |

**Still open:**
- A person needs to check the privacy answer key (P2).
- The test files have not been scored (P5).
- Her notes also list pricing and liability as example topics, so narrowing to one category should be confirmed with her (P1).

---

## R. Reading the pages

**R1. Use the PDF's own text where it exists, and OCR on scans.** A digital page stores its text exactly. A scanned page
is only a picture, so OCR (software that guesses letters from a picture) has to read it.
- **Telling them apart:** a page counts as scanned when one image covers at least 90% of it and it stores fewer than 40
  words. Result: 47 scanned pages, 109 digital.
- **Hidden text:** DocuSign stores invisible white tags on top of names, which turned "Jessie Combs" into "J\ecslmsie-n
  C1o\ mbs". White text is dropped only when nothing coloured is behind it, because "Billing Summary" is white on blue.
  On the four sample pages inspected, everything dropped was a tag.

**R2. Make page pictures at 300 dpi.** That's the usual standard for OCR, and the earlier pipeline used 216. Every engine
reads the same pictures, so the comparison is fair.

**R3. Compare three free OCR engines against the earlier pipeline.** Apple Vision is built into Macs. Tesseract runs on
any computer. RapidOCR is the old pipeline's engine, run on its own to see whether the engine or the setup was the
problem. Paid cloud OCR was left out because it costs money per page and sends contract pages to an outside company.

**R4. Score letters with a sample of typed lines.** Two random lines from each scanned page were cut out and typed from
the picture, without seeing any engine's output (93 lines scored). This key only tests letters. Each row is one printed
line, so it says nothing about whether sentences come out whole. Step C covers that, so this key needs no more checking.

**R5. Three scores for each engine.**
- **Character error rate:** letter fixes needed, divided by line length. 5% means one letter in twenty is wrong.
- **Words found:** the share of a line's words that appear anywhere on the engine's page.
- **Numbers exact:** the share of numbers read exactly right. "3,292" vs "3,202" is one letter but a real error.

A second test OCRs pictures of 99 digital pages and compares with their stored text. It needs no hand work, though
digital pictures are easier than real scans. Text a reader can't see (coded characters, hidden tags, dot leaders) is
left out, removing 39 of 3,335 lines.

**R6 and R7. For running text, use Tesseract first, and let Apple Vision fill its gaps.**

| Reading | Scans: letters wrong | Scans: numbers exact | Digital: letters wrong | Digital: numbers exact |
|---|---|---|---|---|
| Earlier pipeline | 8.8% | 61% | not tested | not tested |
| RapidOCR, 300 dpi | 5.1% | 98% | 4.5% | 95.5% |
| Apple Vision | 3.0% | 98% | 1.06% | 95.5% |
| Tesseract | 0.65% | 98% | 0.65% | 95.5% |
| **Tesseract + Vision** | **0.37%** | **100%** | **0.39%** | **97.6%** |

Why combine them:
- **Apple Vision** reads most lines perfectly but sometimes skips a whole block with no warning (half of F03 p3).
- **Tesseract** is steady on normal text but can't read text on grey or coloured backgrounds.

So Vision fills only the spots where Tesseract found nothing or was under 60% sure. The combination was designed on the
scanned-page key, so that score is a little optimistic. The digital test played no part in the design and ranks the
readings the same way.

**R8. Tested, not adopted: a dictionary vote between engines.** Keeping whichever version had more real words changed 43
lines and no score. It fixed some words ("violation") and added others' errors ("AP!").

---

## T. Tables

**T1. Take the printed numbers as correct.** My choice on Nov 14. The table step reads rows and columns and does not test
the numbers: quantities, prices and amounts are assumed right as printed.

**T2. Read tables by position.** Find the header row by its column names, then put each word under the header that is
horizontally nearest. A row can wrap onto several printed lines, so rows are built around their one amount:
- Between two lines holding an amount there is exactly one boundary between rows, and it is the widest gap between
  them, because wrapped lines sit close together and rows have padding. Lines above it join the upper row, lines below
  it the lower row, whichever way a cell wraps.
- Lines above the first amount or below the last one join only if their gap is the size of a gap inside a row, judged
  against the table's own gaps, so a page number under the table stays out.
- No fixed spacing is assumed, since OCR engines measure text height differently. Billing Summaries (T6) use the same
  rule. This replaced "join the nearest amount line" on Nov 14 (what_failed.md, 42).

This is compared with Docling's table model, used by the earlier pipeline.

**T3. Both methods share two rules, to keep the comparison fair.** "Ext. Price" on older forms means the amount, and a
price still counts if OCR misread the currency ("USE 12,000.00").

**T4. Re-read a cell that comes out empty.** Page-wide OCR skips lone characters, like the "1" in a quantity cell. Such a
cell is cut out and read alone, by up to three readers. This recovered all 6 empty quantities, but the order was chosen
on those same 6 cells. The cut-out is trimmed to the ink inside it, so a lone "1" in a tall row is still read
(what_failed.md, 42).

**T5. Use Apple Vision for tables.** Table headers sit on grey shading, which Tesseract can't read, so it misses whole
tables. The best reading for paragraphs isn't the best for tables.

| Table reader + OCR | Product rows found | Rows with no quantity read |
|---|---|---|
| Docling (old) | 86 | 2 |
| Position + Tesseract | 20 | 0 |
| Position + Tesseract and Vision | 67 | 4 |
| Position + Vision, no re-read | 88 | 6 |
| **Position + Vision + cell re-read** | **88** | **0** |

Docling missed F03's Year 5 block (what_failed.md, 8). The design was improved on these same files.

**T6. Billing Summary tables are read on their own.** F13 and F14 have this table, with no quantity or price column, so
the pricing reader skipped it. On F13 it came out as "sD 6720050" for USD 67,260.50. It's now found by its own header,
and its rows are grouped by the same rule as pricing tables (T2): `outputs/tables/billing_rows.csv`.

---

## F. Order-form fields

**F1. Read eight fields from 14 order forms:** order number, order date, customer, billing frequency, payment terms, grand
total, signer's name and signing date. The answer key was typed from the page pictures. **I checked all 112
values against the pictures on Nov 2 and changed none** (page: `python -m bench.review forms`). It holds 99 values on the page and 13 that aren't (11 blacked out, 2 never there). Reporting one of those 13
counts as inventing a value. It includes traps: earlier order numbers mentioned in notes, and a crossed-out signer.

**F2. Compare two methods reading the same text, and their combination.**
- **Text rules:** search the running text for a label and take what follows. Simple, but side-by-side columns blur.
- **Layout:** find the label on the page and take the words beside it. Keeps columns apart, but can't find a value inside
  a sentence.
- **Layout + text rules:** layout first; a header field it can't find is searched for in the running text (F5).

**F3. Layout + text rules is the most accurate.** First versions scored 76.8% (text rules) and 61.6% (layout); general
fixes found on these same forms raised them (F5), so these are development scores.

| Field (values on the page) | Text rules | Layout | Layout + text rules |
|---|---|---|---|
| Order number (12), order date (14), billing frequency (12) | all right | all right | all right |
| Customer (14) | 12 | **14** | **14** |
| Payment terms (14) | **14** | 12 | **14** |
| Grand total (14) | 14 | 14 | 14 |
| Signer's name (9) | 3 | **8** | **8** |
| Signing date (10) | 3 | **10** | **10** |
| **All 99 values** | 84, 1 invented | 96, 0 invented | **98, 0 invented** |

No method fell for the earlier order numbers. The one value still wrong is a handwritten name: "Angela Fredrickson" read
as "Angela Fredriceson" (OF03).

**F4. How the two compare on her criteria.**

| | Text rules | Layout |
|---|---|---|
| Manual work | Low: one pattern per field | Medium: labels plus position rules |
| Easy to understand | Yes | Yes |
| Consistency | Breaks when columns change | Breaks when a value is inside a sentence |
| Cost | None | None |

They fail in different places, so the combination beats both (F3).

**F5. Fixes from looking at every value layout got wrong (Nov 14).** Each fix is a general rule, not a patch for one form:
- **A wide gap ends a value.** After a value's first word, a gap wider than about three letters starts the next
  column. "Billing Contact:" is two words and only the second ends in ":", so "Billing" had joined the customer's name.
- **A field not found is looked up in Apple Vision's reading.** The paragraph reading lost the "Date:" of two signature
  blocks (OF04, OF13). Vision alone skips other blocks, so it is the second reading, not the first.
- **Signature-block values are read again on their own**, enlarged, by Apple Vision, as empty table cells are (T4).
  Handwriting is read much better alone: "7/29/2016" and "Paul Turman" are now right.
- **Crossed-out words are blanked before that read.** A dark line through the middle of words that stays on them is a
  strike; the printed line to write on can pass through handwriting too, but runs well past it. On all 14 forms only
  OF13's crossed-out "Cheri Polenske" is flagged.
- **Layout + text rules** takes a header field layout can't find from the running text, but only for fields the
  running-text search reads without error (order number, order date, billing frequency, payment terms, grand total).
  This finds "Net 30" inside a sentence (OF01, OF02).

---

## C. Clean text

Printed lines aren't usable text: sentences stop at line ends, page numbers sit among the words, and table cells float
alone. I found this on Oct 29, so this step rebuilds whole text.

**C1. Remove clutter, log every removal, and lean toward keeping text.** Anything with a real word of four or more
letters, a number of three or more digits, or a tick mark is never removed by the clutter rule. Removals are listed with
reasons in `outputs/text/removed.csv`.

| Removed | Count |
|---|---|
| Page numbers | 69 |
| Empty form fields (C7) | 46 |
| DocuSign stamps | 41 |
| Symbols, signature underlines, logos read as letters | 40 |
| Repeated headers and footers | 32 |
| Very unsure OCR that Apple Vision didn't confirm (C7) | 20 |
| Empty section ("Notes") (C7) | 1 |

**C2. Take tables from the table step.** Its rows replace a second reading, so "Per Year" stays in its row.

**C3. Keep columns and form rows together.** A line splits where two words are far apart. Pieces on one row stay together
as `label | value`. Two exceptions: a clause number set apart from its text, and a line continuing an unfinished sentence.

**C4. Join lines into paragraphs, also across pages.** A new paragraph starts at a wider gap, a new column, or a numbered
clause after a finished sentence. A paragraph ending a page in mid-sentence continues on the next page (23 times).

**C5. Count each problem before and after.**

| Problem, all 14 files | Before | After |
|---|---|---|
| Page numbers and stamps in the text | 88 | 0 |
| Sentences cut off | 2,119 | 10 |
| One- or two-word pieces outside tables and forms | 1,004 | 118 |

Most of the 118 are real headings and labels. A third OCR engine, not used to build the text, finds only 3 lines missing
and 30 misread words. These counts come from the cleaning rules themselves, so they don't prove the text is right. C6 does.

**C6. Check by reading whole pages.** A person reads the clean text beside the scan, which replaces line-by-line checking.
Done for F02 and F13. A digital order form would add confidence.

**C7. My check of F02 led to three narrow rules.**
- **Scraps not on the page** ("eis", "£5"): lines Tesseract is under 30% sure of, where Vision saw nothing, are removed (20
  lines, all garbage).
- **Empty fields** ("Billing Contact:"): dropped only inside a side-by-side form row, when not in capitals, with nothing
  below and no value nearby. A broader rule had removed labels whose values are printed below them.
- **Empty sections** ("Notes"): dropped only if one or two words, left-aligned, last on the page, with at least a tenth of
  the page blank below. A broader rule had removed signers' titles.

Being narrow, these rules may leave a few empty labels in other files. That's the safer failure.

**C8. My check of F13, the poorest scan, led to one fix:** the Billing Summary (T6). Misspellings, split product
descriptions and garbled handwriting remain. I judged these not major.

---

## P. Finding the privacy passages

**Words used in this section**
- **Block:** one piece of the clean text (section C): a paragraph, a heading, a form (rows of `label | value`) or a
  pricing table.
- **Section:** a run of blocks about one clause, used in P3–P7. A new section starts at a heading, a form, a table, a
  numbered clause ("8. Compliance.") or a run-in title ("Duration: …"). The last two are found with regular expressions
  (regex: a written text pattern the code searches for).
- **Tuning files** (F01–F06, F09, F11, F12): used to build and adjust the methods. **Test files** (F07, F08, F10, F13,
  F14): scored once, at the end.

**P1. One category: data governance and privacy.** My decision on Nov 2, so a 12-topic plan was dropped. Semantic
similarity and Llama are given this definition word for word:
> Data governance and privacy: who owns customer, student or user data; how the vendor may use, analyze or share it,
> including aggregated or de-identified data and training AI models; disclosure to third parties; how long data is kept
> and how it is exported, returned or deleted; security safeguards and data breach notification; and duties under
> privacy laws such as FERPA and GDPR.

**P2. The answer key: 83 passages marked** (`data/gold/privacy_passages.csv`), before any method was built.

| Group | Passages | Meaning | Example |
|---|---|---|---|
| Core | 49 | Clearly in the category; must be found | "9. Aggregated Data. As between the parties, Instructure owns…" |
| Borderline | 25 | Could go either way, so a person decides; counts neither for nor against a method | Ordinary business confidentiality; password duties |
| Not scored | 9 | In the F09 security brochure, which is marketing, not signed terms | — |

Only blocks containing a broad set of related words were read in full, so a passage with none of those words could be
missing. **A person still has to check the key:** `outputs/privacy/privacy_key_for_review.xlsx`, for my mentor.

**P3. Three methods decide whether text is in the category.**

| Method | Keeps the text when | Tool |
|---|---|---|
| **Term list** | It contains a privacy term ("personal data", "FERPA", "data breach", "encrypt"…), or "Customer Content" within 6 words of a word such as own, use, secure, export or delete | Two regexes, written from the tuning files |
| **Semantic similarity** | Its meaning is close to the definition in P1: both are turned into lists of numbers (embeddings), and their similarity score (higher = closer) is at or above a threshold | sentence-transformers, all-mpnet-base-v2 |
| **Llama** | Llama answers yes when asked whether the text is in the category defined in P1. It must reply in a fixed form a program can read (JSON): `{"in_category": true}` or `false` | Llama 3.1 8B Instruct, on the lab server |

In the code and result files, semantic similarity is still called `meaning`.

At first each method judged whole sections (P6, P7); now each judges one block at a time (P8). For sections, each
method cut the file its own way:
- **Term list:** the regex sections defined above.
- **Semantic similarity:** a new section where two neighbouring blocks differ in meaning (similarity below 0.7).
- **Llama:** Llama is shown 30 blocks at a time and asked where sections start.
- **Regex sections + Llama:** the term list's sections, judged by Llama. This separates Llama's cutting from its judging.

**P4. Four scores, counted in words.** Example: the key has 300 core words, and a method returns 200 words, of which 150
are core, 20 borderline and 30 neither.
- **Found** = core words returned ÷ all core words in the key = 150 ÷ 300 = 50%. This matters most: what is missed never
  reaches extraction.
- **Clean** = core words returned ÷ words returned, leaving borderline words out = 150 ÷ (200 − 20) = 83%.
- **Whole** = the share of core passages returned complete, meaning every block of the passage was returned. Half a
  clause can lose its meaning.
- **F2** = found and clean in one number, with found counted twice as much: 5 × found × clean ÷ (4 × clean + found). For
  found 100% and clean 49%, F2 = 0.83. Used only to pick the semantic-similarity thresholds.

The F09 brochure is left out of every score. Scored with it, semantic similarity kept only brochure text and found no
contract clause (what_failed.md, 36).

**P5. Test fairly.** Methods are built and adjusted on the tuning files (15 core and 12 borderline passages). The test
files are scored once, after the key is checked. The term list came from the tuning files only, so a term seen only in
test files ("Service Data") was left out on purpose. Three limits: the test files were read while cleaning the text
and drafting the key; some standard wording appears in both groups; and on Nov 2–3, F07, F08 and F10 were briefly used
as tuning files, then put back as test files. Everything changed because of them was undone (a "security breach" term
and two additions to the keep-together rule), but their results were seen, so the test on them is not fully blind.

**P6. First results, judging sections (tuning files).**

| Method | Found | Clean | Whole |
|---|---|---|---|
| **Term list** | **100%** | 49% | **100%** |
| Semantic similarity | 73% | 64% | 67% |
| Regex sections + Llama | 66% | 79% | 33% |
| Llama | 49% | 73% | 33% |

- **The term list returns whole clauses:** "8. Compliance." comes back complete, though only its second sentence (on
  security safeguards) is about data. The rest of the clause lowers clean.
- **Llama's sections were too big:** on F01 it made clauses 1–10 one 1,159-word section and said no, losing "9.
  Aggregated Data." Judging the regex sections instead raised found from 49% to 66%.
- **Llama and semantic similarity miss a privacy sentence inside a clause about something else:** "8. Compliance." and "16.
  Termination.", whose last sentence lets the customer export its data for 3 months.
- **These scores are optimistic:** 15 passages, F01 and F02 share wording, the term list was written from these files,
  and only one Llama prompt was tried.

**P7. The sorter: three votes, and a person checks where they disagree.** My goal: all core text found, a person
checks borderline text, and as little reading as possible.
1. **Vote.** Each piece gets up to three votes: the term list keeps it; Llama says yes; its similarity score is at or
   above a threshold t.
2. **Sort.** 2–3 votes: automatically in. 0 votes: automatically out. 1 vote: a person reads it.
3. **Tune on the tuning files.** Try t from 0.20 to 0.70 in steps of 0.05, 2 or 3 votes for automatically in, and with
   or without a wide net (a 0-vote piece containing a broad word such as "data", "records" or "confidential" goes to a
   person instead of out). Keep only settings where all core text is found after checking and enough borderline text
   reaches a person: 95% on sections, 85% on blocks (P8). Of those, pick the one with the fewest words a person reads
   plus wrong words let in automatically.

On sections the chosen setting was t = 0.45, with a person reading 11.8% of the words (40 sections). The current results,
on blocks, are in P8.

**The research behind this approach:**
- Sending uncertain cases to a person: [Chow 1970](https://dblp.org/pid/85/786).
- Fixing a limit, then automating as much as possible: [Geifman & El-Yaniv 2017](https://arxiv.org/abs/1705.08500).
- Software-assisted legal review: [Grossman & Cormack 2011](https://scholarship.richmond.edu/jolt/vol17/iss3/5/).
- Judging review against a recall target: [Cormack & Grossman 2016](https://cormack.uwaterloo.ca/reliability).

These support the general approach. The voting rule, the borderline limit and counting a word read the same as a wrong
word let in are my own choices, kept simple because 15 passages can't support a fitted model.

**Limits:**
- It assumes a person always agrees with the key.
- It rests on 15 passages, so "100% found" is optimistic.
- The cliff in P8 suggests the setting may be fragile on new files.
- Nobody sees the automatically-out text, so on the test files a person should spot-check a random sample (an
  [elusion test](https://relativity.com/blog/active-learning-validation-101-quantifying-your-success/)). Practitioners warn
  this test alone can overstate how much was found.

**P8. Judge one block at a time (the current design).** My choice on Nov 2. Sections carried unrelated text along
(F01's price deadline rode inside "Miscellaneous"), and Llama's own sections were too big (P6).
- **Each block is judged on its own**, with two exceptions:
  - **Headings are never judged or returned.** They name a topic but state no term, and no core passage is a heading.
  - **Form rows on one page that a wide gap split apart stay one form**, so a signature box stays together.
- **Llama sees context above the block:** the nearest heading, the opening of its clause, and the nearest lead-in line
  ending in ":". For "(b) If the refund is due to a Provider Error…", that lead-in is "8.3 Refunds and Chargebacks. If an
  Individual Requestor seeks a refund…:". The context helps Llama understand the block and is never returned or scored.
  Headings containing a digit ("Year 1") are labels, not topics, so they are skipped.

| Tuning files | Found | Clean | Whole | Before, on sections |
|---|---|---|---|---|
| **Term list** | **100%** | **69%** | **100%** | 100%, 49%, 100% |
| Semantic similarity | 73% | 51% | 67% | 73%, 64%, 67% |
| **Llama, with context** | **73%** | **100%** | 53% | 49%, 73%, 33% |

- **Term list:** cleaner, because unrelated parts of a clause no longer ride along.
- **Semantic similarity:** less clean, because a short block gives it little to go on.
- **Llama gains the most:** nothing it keeps is wrong. It still misses "8. Compliance."

**The sorter on blocks.** With the 95% borderline limit, a person would read 33.8% of the words (66 blocks). **I chose
the lighter check (Nov 2):** an 85% limit, which picks t = 0.45 with two votes for automatically in and no wide net. The
cost is 3 borderline passages that get no vote and go out unseen: "14. Feedback" (customer surveys) in F01 and F02, and
F12's term on confidentiality of public records.

| Sorter on blocks, tuning files (25,269 words) | |
|---|---|
| Core found after checking | 100% |
| Core found with no person involved | 87.8% |
| Borderline reaching a person | 88.8% |
| A person reads | 8.6% of the words (14 blocks) |
| Automatically out | 88.0% of the words |
| Automatically-in text that is core or borderline | 90.3% |

The chosen setting sits just before a cliff:

| t | A person reads | Borderline reaching a person | Core found after checking |
|---|---|---|---|
| 0.40 | 14.6% | 88.8% | 100% |
| **0.45** | **8.6%** | **88.8%** | **100%** |
| 0.50 | 5.0% | 49.9% | 100% |

**P9. Keep blocks, but keep a passage's pieces together.** My choice on Nov 2.

**The problem:** judging one block at a time can keep a lettered item ("(c) … delete Customer Data within 30 days") and
drop its lead-in ("The vendor shall:"), so the reader loses who must do what. The tuning files can't show this, because
all 15 of their core passages fit inside one block. On the test files, 9 core passages run across 2 to 11 blocks.

**Considered: going back to sections (P3–P7).**

| Tuning files | Sections | Blocks |
|---|---|---|
| Term list: found / clean | 100% / 49% | 100% / 69% |
| Llama: found / clean | 66% / 79% | 73% / 100% |
| A person reads | 11.8% of words (40 sections) | 8.6% (14 blocks) |
| Borderline reaching a person | 98.3% | 88.8% |
| A passage inside one clause returned complete | Always, once any part is kept | Not guaranteed |

I kept blocks, because sections bring back subclauses and sentences that have nothing to do with privacy.

**Added instead: a keep-together rule**, the last step after a method or the sorter has chosen its blocks. It works
inside one clause (one regex section) only:
- The first kept block brings its **lead-in**: the nearest line above it ending in ":".
- Every block **between two kept blocks** comes too.
- Items between the lead-in and the first kept block stay out, and nothing comes from another clause.
- In the sorter, a block brought along by automatically-kept blocks is kept automatically; one brought along with the
  help of a block a person checks goes to that person too.

Example, on made-up text. Each line is its own block; "6." starts a new block and a new clause.
- Clause 5: "5. Security. The vendor shall:" / "(a) encrypt Customer Data at rest;" / "(b) keep accurate invoices;" /
  "(c) delete Customer Data within 30 days of termination."
- Clause 6: "6. Data Return. Instructure will return Customer Data on request."

| Blocks a method keeps | Returned after the rule | Why |
|---|---|---|
| (c) | The lead-in and (c) | (a) and (b) sit between the lead-in and the first kept block, so they stay out |
| (a) and (c) | The lead-in, (a), (b) and (c) | (b) lies between two kept blocks of one clause, though it isn't about privacy |
| (a) and "6. Data Return." | The lead-in, (a) and "6. Data Return." | (b) and (c) are not added: gaps are filled only inside one clause |

Every block and its result: `outputs/privacy/blocks_segmented.xlsx`, made by `python -m bench.review blocks`.

**Effect on the tuning files:** no contract block is added, for any method or for the sorter, so every score above is
unchanged. It adds a few blocks inside the unscored F09 brochure. The rule was fixed before the test files were scored,
so its benefit will be measured there without having been tuned on them.

**Limits:** it can't recover a passage whose blocks were all missed; it can't add an item that comes after the last
kept block; and if (a) and (c) are about privacy but (b) isn't, (b) is returned too.

**P10. Check the pipeline against a person's judgement.** Added on Nov 14, after my mentor's feedback on the diagram.
A person answers one question for every block, without seeing the three votes: is it about data governance and
privacy, yes or no? The answers come from the answer key (P2). Then the final privacy blocks are set against those
answers. The person is not a fourth vote: their answers never decide what is kept; they only measure how often the
pipeline gives the same answer.

| Tuning files, blocks | Person: privacy | Person: not privacy |
|---|---|---|
| In the final privacy blocks | **24** | 0 |
| Not in them | 3 | **460** |

- **484 of 487 blocks match.** No block the person calls not privacy reaches the final blocks.
- **The 3 misses** are dropped automatically, with no vote: "14. Feedback" (customer surveys) in F01 and F02, and F12's
  term on confidentiality of public records. They are the cost of the 85% limit chosen in P8.
- **14 of the blocks were decided by the person who checks** (the middle pile, P7), who is assumed to answer like the
  key, so those match by design. The real test is the other 473, decided automatically: 470 match.
- **Why a table and not one percentage:** 460 of the 487 blocks are plainly not privacy, so a pipeline that dropped
  everything would still match on 94%. The two cells that matter are privacy left out (lost for good) and not privacy
  kept (noise passed to Goal 2).

Two rules for the person's answers:
- **Borderline counts as yes for now.** The key marks 25 passages "borderline" (could go either way). The review
  workbook asks my mentor to answer each one yes or no; until then they count as privacy, since losing privacy text is
  the costlier mistake.
- **A lead-in counts as privacy when the items under it are.** The keep-together rule (P9) returns lines like "The
  vendor shall:", which say nothing about privacy on their own. None occur on the tuning files, but they will on the
  test files.

`python run.py privacy` writes this table, in blocks and in words and split by who decided, to
`outputs/privacy/agreement_tune.csv`.

**This does not yet show the pipeline is robust:**
- The key still needs a person's check (P2); until then, the person's answers are the key's first answers.
- Matching on the tuning files is expected. The term list was written from them, and the key was drafted by reading in
  full only blocks with related words. The term list alone also matches the key on every tuning block that is not
  borderline.
- The real test is the test files: `python run.py privacy-test` writes the same table to `agreement_test.csv`.
- A privacy block with none of the related words would be missed by the key and the pipeline alike, so the table
  can't see it. Only a person reading a random sample of the automatically-dropped blocks can (P7, limits).

---

## S. Where things run

**S1. Mac for Apple Vision, lab server for heavy work.** Vision only runs on a Mac, so its saved readings travel in the
bundle. The server ran RapidOCR's last pages, the embeddings and Llama, and those raw answers are saved in
`work/privacy`, so scores can be rerun in seconds without the server. Someone without a Mac can rerun everything except
the Vision reading itself.
