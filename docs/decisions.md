# Decision log

What was decided at each step, why, and what happened. IDs like R7 are referred to in the code. The failures behind
these decisions are in [what_failed.md](what_failed.md).

## At a glance (Nov 2, 2026)

| Step | Decision | Result so far |
|---|---|---|
| Read pages | PDF's own text where it exists; OCR on scans | 0.37% of letters wrong on scans (old pipeline: 8.8%) |
| Pricing tables | Read by column position, checked with arithmetic | 88 rows; all 63 subtotals and 12 grand totals add up |
| Order-form fields | Find each label on the page, take the value beside it | 89 of 99 values right |
| Clean text | Remove page clutter, join lines into whole paragraphs | Cut-off sentences: 2,119 → 10 |
| Privacy passages | Three methods vote; a person checks where they disagree | All core text found; a person reads 11.8% of the words (tuning files) |

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

**T1. Check pricing tables with arithmetic.** These checks need no hand labels: quantity × price = amount on each row,
rows add up to subtotals, and everything adds up to the grand total. A wrong digit or a lost row breaks one of them.

**T2. Read tables by position.** Find the header row by its column names, then put each word under the nearest header. A
row can wrap onto several printed lines, so each row is built around the line holding its amount. This is compared with
Docling's table model, used by the earlier pipeline.

**T3. Both methods share three rules, to keep the comparison fair.** "Ext. Price" on older forms means the amount. A flat
fee with no quantity passes when price = amount. A price still counts if OCR misread the currency ("USE 12,000.00").

**T4. Re-read a cell that comes out empty.** Page-wide OCR skips lone characters, like the "1" in a quantity cell. Such a
cell is cut out and read alone, by up to three readers. This recovered all 6 empty quantities, but the order was chosen
on those same 6 cells.

**T5. Use Apple Vision for tables.** Table headers sit on grey shading, which Tesseract can't read, so it misses whole
tables. The best reading for paragraphs isn't the best for tables.

| Table reader + OCR | Row checks | Subtotals | Grand totals | Rows found |
|---|---|---|---|---|
| Docling (old) | 78/86 | 60/60 | 7/8 | 86 |
| Position + Tesseract | 19/20 | 13/13 | 4/4 | 20 |
| Position + Tesseract and Vision | 60/67 | 37/40 | 7/11 | 67 |
| **Position + Vision + cell re-read** | **81/88** | **63/63** | **12/12** | **88** |

**T6. The 7 failing rows are errors in the contracts.** Each was checked against the page: for example, 400 users ×
$7,500.00 is printed as $7,500. So there are no known reading errors in the 88 rows' numbers. Descriptions and dates
aren't tested by arithmetic. The design was improved on these same files, so these are development scores.

**T7. Billing Summary tables get their own check.** F13 and F14 have this table, with no quantity or price column, so
the pricing reader skipped it. On F13 it came out as "sD 6720050" for USD 67,260.50. It's now read separately, and all 10
arithmetic checks pass.

---

## F. Order-form fields

**F1. Read eight fields from 14 order forms:** order number, order date, customer, billing frequency, payment terms, grand
total, signer's name and signing date. The answer key was typed from the page pictures. **I checked all 112
values against the pictures on Nov 2 and changed none** (page: `python -m bench.review forms`). It holds 99 values on the page and 13 that aren't (11 blacked out, 2 never there). Reporting one of those 13
counts as inventing a value. It includes traps: earlier order numbers mentioned in notes, and a crossed-out signer.

**F2. Compare two methods reading the same text.**
- **Text rules:** search the running text for a label and take what follows. Simple, but side-by-side columns blur.
- **Layout:** find the label on the page and take the words beside it. Keeps columns apart, but can't find a value inside
  a sentence.

**F3. Layout is more accurate, mainly on signatures.** First versions scored 76.8% and 61.6%; general fixes found on these
same forms raised them, so these are development scores.

| Field (values on the page) | Text rules | Layout |
|---|---|---|
| Order number (12), order date (14), billing frequency (12) | all right | all right |
| Customer (14) | 12 | 12 |
| Payment terms (14) | **14** | 12 |
| Grand total (14) | 14 | 14 |
| Signer's name (9) | 3 | **6** |
| Signing date (10) | 3 | **7** |
| **All 99 values** | **84, 1 invented** | **89, 0 invented** |

Neither method fell for the earlier order numbers. Handwriting defeats both, and fixing that needs a stronger reader, not
better rules.

**F4. How the two compare on her criteria.**

| | Text rules | Layout |
|---|---|---|
| Manual work | Low: one pattern per field | Medium: labels plus position rules |
| Easy to understand | Yes | Yes |
| Consistency | Breaks when columns change | Breaks when a value is inside a sentence |
| Cost | None | None |

They fail in different places, so a combination would likely beat both. That hasn't been tested.

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

**C2. Take tables from the table step.** Checked rows replace a second reading, so "Per Year" stays in its row.

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

**C8. My check of F13, the poorest scan, led to one fix:** the Billing Summary (T7). Misspellings, split product
descriptions and garbled handwriting remain. I judged these not major.

---

## P. Finding the privacy passages

**P1. Target one category: data governance and privacy.** My decision on Nov 2, so a 12-topic plan was dropped. The
category covers who owns customer, student or user data; how the vendor may use or share it, including aggregated data
and AI training; disclosure to third parties; retention, export and deletion; security safeguards and breach notice; and
duties under privacy laws such as FERPA and GDPR.

**P2. The answer key has two groups, drafted before any method was built.**
- **Core (49 contract passages):** must be found.
- **Borderline (25):** a person checks these, such as ordinary business confidentiality or password duties. They count
  neither for nor against a method.

Only blocks containing a broad set of related words were read in full, so a passage with none of those words could be
missed. **The key still needs a person to check it:** `outputs/privacy/privacy_key_for_review.xlsx`, for my mentor.

The **F09 security brochure is out of all scoring**, because it isn't contract terms and its many words swamped the scores.

**P3. Compare three methods.** Each splits a file into sections of whole blocks, so signed text is never rewritten.

| Method | Splits at | Keeps a section when |
|---|---|---|
| Rules | Headings, tables, numbered clauses, run-in titles | It has a privacy term |
| Meaning | Where neighbouring blocks change subject | It's close in meaning to the category definition |
| Llama | Where Llama says a section starts | Llama says yes |
| Rules + Llama | As the rules | Llama says yes |

**P4. Score in words.**
- **Found:** the share of core text returned. This matters most, because what's missed never reaches extraction.
- **Clean:** the share of returned text that is core (borderline text isn't counted).
- **Whole:** the share of core passages returned complete in one section.
- **F2:** found and clean combined, with found weighted double. Used only to tune the meaning method.

**P5. Test fairly.** Tune on F01–F06, F09, F11, F12. Test once at the end on F07, F08, F10, F13, F14, after the key is
checked. The rules' term list came from the tuning files only, so terms seen only in test files ("Service Data") were left
out on purpose. Two limits: the test files were read while cleaning the text and drafting the key, and some boilerplate
appears on both sides.

**P6. Alone, the rules lead (tuning files, 15 core passages).**

| Method | Found | Clean | Whole |
|---|---|---|---|
| **Rules** | **100%** | 49% | **100%** |
| Meaning | 73% | 64% | 67% |
| Rules + Llama | 66% | 79% | 33% |
| Llama | 49% | 73% | 33% |

- **Rules** return whole clauses, so "8. Compliance" comes back in full though one sentence is about data.
- **Llama and meaning** miss a privacy sentence inside a clause about something else.
- **These scores are optimistic:** there are few passages, F01 and F02 share terms, and the rules were written from these
  files. Only one Llama prompt was tried.

**P7. Balance score against manual checking with a three-way sorter.** My goal: core must be found, a person checks
borderline text, and that checking stays as small as possible.

1. **Vote.** Each of the rules' sections gets up to three votes: rules, Llama, meaning.
2. **Sort.** 2–3 votes: automatically in. 0 votes: automatically out. 1 vote: the methods disagree, so a person checks it.
3. **Tune.** Limits first: all core found, and at least 95% of borderline reaching a person. Then pick the setting with
   the fewest words a person reads plus wrong words let in. Chosen: a meaning threshold of 0.45.

| Tuning files, 25,607 contract words | |
|---|---|
| Core found after checking | 100% |
| Core found with no person involved | 80.7% |
| Borderline reaching a person | 98.3% |
| A person reads | 11.8% of the words (40 sections) |
| Automatically out | 85.0% of the words |
| Correct among automatically-in text | 89.1% |

The chosen setting sits just before a cliff:

| Meaning threshold | Person reads | Borderline reaching a person | Core found |
|---|---|---|---|
| 0.40 | 20.2% | 98.3% | 100% |
| **0.45** | **11.8%** | **98.3%** | **100%** |
| 0.50 | 8.3% | 59.4% | 100% |

**The research behind this approach:**
- Sending uncertain cases to a person: [Chow 1970](https://dblp.org/pid/85/786).
- Fixing a limit, then automating as much as possible: [Geifman & El-Yaniv 2017](https://arxiv.org/abs/1705.08500).
- Software-assisted legal review: [Grossman & Cormack 2011](https://scholarship.richmond.edu/jolt/vol17/iss3/5/).
- Judging review against a recall target: [Cormack & Grossman 2016](https://cormack.uwaterloo.ca/reliability).

These support the general approach. The voting rule, the 95% limit and counting a word read the same as a wrong word let
in are my own choices, kept simple because 15 passages can't support a fitted model.

**Limits:**
- It assumes a person always agrees with the key.
- It rests on 15 passages, so "100% found" is optimistic.
- The cliff suggests the setting may be fragile on new files.
- Nobody sees the automatically-out text, so on the test files a person should spot-check a random sample (an
  [elusion test](https://relativity.com/blog/active-learning-validation-101-quantifying-your-success/)). Practitioners warn
  this test alone can overstate how much was found.

---

## S. Where things run

**S1. Mac for Apple Vision, lab server for heavy work.** Vision only runs on a Mac, so its saved readings travel in the
bundle. The server ran RapidOCR's last pages, the meaning vectors and Llama, and those raw answers are saved in
`work/privacy`, so scores can be rerun in seconds without the server. Someone without a Mac can rerun everything except
the Vision reading itself.
