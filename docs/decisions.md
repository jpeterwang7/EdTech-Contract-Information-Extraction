# Decision log

Every choice made so far, in order: what the options were, what was picked, and why. Each entry has an ID
(R = reading the pages, T = tables, S = server) that the code refers to. Numbers come from the files in
`outputs/`; the failures behind them are told in [what_failed.md](what_failed.md).

**Status (Oct 29, 2026):** steps R (reading), T (tables) and F (order-form fields) are built and scored.
Two answer keys still need a person to check them: OCR lines (R4) and order-form fields (F1).

---

## Reading the pages (R)

### R1. Read every page twice: as stored text and as a picture

**The problem.** A PDF page is one of two things. A *digital* page stores its text, and a computer can copy it out
exactly. A *scanned* page is only a photograph of paper, and a computer sees dots, not letters. To get letters
from a photograph you need OCR (optical character recognition): software that looks at the picture and guesses
each letter.

**What we did.** For each of the 156 pages we copied out any stored text (the "text layer"). We also made a
picture of the page, so OCR could read it.

**How we decide a page is scanned.** It is scanned when one image covers at least 90% of the page **and** the
stored text has fewer than 40 words. We need both conditions:
- Some scans carry a few real words on top (DocuSign stamps an "Envelope ID" on every page), so "no text at all"
  is too strict.
- One digital page (F09 p13) has only 36 words but no image, so "few words" alone would be wrong.

**Result.** 47 scanned pages and 109 digital pages (`outputs/reading/page_inventory.csv`). Digital pages always
use their stored text, which is exact. Everything below about OCR is about the 47 scanned pages.

**Hidden text is left out.** DocuSign stamps invisible field tags onto the order forms it handles:
`/BillingContactName1/`, `\n1\` (a name), `\d1\` (a date). They are stored as white text on the white page, right
on top of the visible names and dates. Copied out naively, "Jessie Combs" came out as "J\ecslmsie-n C1o\ mbs".
So white characters are dropped, **but only when nothing coloured is behind them**. The first version dropped all
white text, and that also removed the visible heading "Billing Summary", which is printed white on a blue bar (see
what_failed.md, 17). Checked by hand: everything the rule drops is a tag, on 14 pages of 4 files (F07, F11, F12,
F14).

### R2. Make page pictures at 300 dpi

dpi = dots per inch, the sharpness of the picture. 300 dpi is the usual standard for OCR. The earlier pipeline
used 216 dpi. Sharper pictures help OCR but take more memory and time. We kept 300 for every engine so that the
engines are compared on the same pictures.

### R3. Compare three OCR engines against the earlier pipeline

| Reading | What it is | Why it is in the test |
|---|---|---|
| baseline | the earlier pipeline's output (Docling + RapidOCR, 216 dpi) | the thing to beat |
| RapidOCR | the same engine, at 300 dpi, on its own | was the old problem the engine or the setup around it? |
| Apple Vision | the OCR built into macOS | free and strong, but only runs on a Mac |
| Tesseract 5 | the best-known free OCR (Google, open source) | free and runs on any computer |

We did not test paid cloud OCR (Google, Amazon, Azure). It costs money per page, and it sends contract pages to an
outside company.

### R4. Answer key 1: 94 lines from scanned pages, typed from the picture

To score an engine you need the true text: an *answer key*.
- **Picking lines.** We picked 2 lines on each of the 47 scanned pages at random: one from the lines Apple Vision
  found and one from the lines Tesseract found. Taking half from each means neither engine alone decides which
  text gets tested.
- **Typing the answers.** Each line was cut out as a small picture and typed from that picture
  (`data/gold/ocr_crops/`). The typist never saw any engine's output, so the key does not lean toward any
  engine.
- **What's left out.** One line was a handwritten signature. We left it out, because signatures are not text we
  need to extract.
- **Mix.** 41 lines of paragraph text, 24 table cells, 15 form fields, 7 headings and 6 page footers.
- **⚠ Still to do:** I should check every typed line against its picture
  (`human_checked` column in `data/gold/ocr_lines.csv`) and record how many were changed.

### R5. How a reading is scored

A single line is scored against the whole page an engine read, because engines split and order lines
differently. First we find the stretch of the engine's page text that best matches the true line (the
"alignment"). Then:
- **Character error rate (CER):** how many single-letter fixes (add, delete or change a letter) turn the engine's
  stretch into the true line, divided by the line's length. 0% is perfect; 5% means one letter in twenty is wrong.
- **Words found:** the share of the true line's words that appear anywhere in the engine's page, in any order.
  This forgives an engine that read a table column by column instead of row by row.
- **Numbers exact:** the share of the true line's numbers (prices, dates, quantities) that the engine got exactly
  right. For contracts this matters most: "$3,292" vs "$3,202" is one letter but a real error.

Before comparing, both texts get the same quote and dash characters (curly “ ” vs straight " are typesetting, not
reading errors) and single spaces.

**Answer key 2 (digital pages).** We also OCR'd the pictures of the 109 digital pages and compared the result with
their stored text. This needs no hand work and covers thousands of lines. But clean digital pictures are easier
than real scans, so it shows each engine's best case.

**Which digital pages are used.** The 99 digital pages with at least 100 stored words whose words are at least 70%
real English. The real-English share is checked against a 234,456-word dictionary, after taking off endings like
-s and -ing. This cut-off would catch a garbled text layer. None of these files has one: the lowest page, an order
form full of names like "Hendrickson" and "UNMC", scores 77%.

Some stored text is never visible on the page, so it can't be the answer for what the page shows. We leave out
lines with:
- characters stored as codes (`(cid:182)`),
- DocuSign's invisible signature tags (`\s1\`),
- table-of-contents dot leaders.

That removes 39 of 3,335 lines.

### R6. Results on answer key 1 (scanned pages)

| Reading | Character errors | Lines perfect | Words found | Numbers exact |
|---|---|---|---|---|
| baseline (earlier pipeline) | 8.8% | 67% | 94.0% | 61% |
| RapidOCR, 300 dpi | 5.1% | 90% | 97.0% | 98% |
| Apple Vision | 3.0% | 89% | 97.2% | 98% |
| Tesseract | 0.65% | 88% | 99.2% | 98% |
| **Tesseract + Vision (R7)** | **0.37%** | 89% | **99.5%** | **100%** |

What the table says, in plain words:
- **The old pipeline's problem was the setup, not the engine.** The same engine (RapidOCR) at 300 dpi cut errors
  almost in half and got numbers right 98% of the time instead of 61%.
- **Apple Vision reads most lines perfectly, but now and then skips a whole block of text without any warning.**
  It skipped half of one page (F03 p3) and a paragraph on another (F13 p3). Missing text is the worst kind of
  error for this project, because nothing tells you it is gone.
- **Tesseract is very steady on normal text, but cannot read text on grey or coloured backgrounds.** It fails on
  shaded headings like "TAX INFORMATION", white-on-red "June 2022", and the logo.

### R7. For running text: Tesseract first, Apple Vision fills the gaps

The two engines fail in different places, so we combine them:
- **Start** with Tesseract's lines.
- **Fill gaps:** add each Apple Vision line that lands where Tesseract found nothing.
- **Replace unsure lines:** where Tesseract was unsure of a line (its own confidence below 60%) and Vision has
  one in the same spot, use Vision's.

On answer key 1, this has the fewest errors of all readings (0.37%) and gets every number right.

**Honest caveat:** the combination was designed after seeing which lines each engine got wrong on this same key,
so its score is a little optimistic. Answer key 2 is the cross-check, because it was not used to design anything.

**The cross-check agrees.** Answer key 2: 785 lines from the 99 digital pages, scored against the PDFs' own text.

| Reading | Character errors | Lines perfect | Words found | Numbers exact |
|---|---|---|---|---|
| RapidOCR, 300 dpi | 4.5% | 85% | 97.8% | 95.5% |
| Apple Vision | 1.06% | 89% | 99.3% | 95.5% |
| Tesseract | 0.65% | 89% | 99.3% | 95.5% |
| **Tesseract + Vision** | **0.39%** | **90%** | **99.6%** | **97.6%** |

Same order as on the scanned pages, so the combination is not just tuned to answer key 1. (These numbers come after
hidden DocuSign tags were removed from the stored text (R1); before that, the tags made every engine look worse on
numbers, e.g. 95.0% for the combination.)

The remaining misses are 7 numbers on 3 lines, all short isolated items: the row labels "S4" and "S6" with their
lone "1" quantities (F14 p4), and one order number read out of order (F12 p2). This is the same weakness T4 fixes
for pricing tables.

---

## Pricing tables (T)

### T1. Start with pricing tables, and use arithmetic as a free answer key

Every Instructure order form prices its products in tables with the same columns (Description, Start Date, End
Date, Metric, Qty, Price, Amount), followed by Sub-Total, Year Total and Grand Total rows. The arithmetic gives
three checks that need no hand labels:
- **Row check:** Qty × Price = Amount on every product row.
- **Subtotal check:** the product rows above a Sub-Total or Year Total add up to it.
- **Grand-total check:** all product rows of an order form add up to its Grand Total.

A wrong digit, a lost row or a value in the wrong column breaks at least one of them.

### T2. Two ways to read a table

- **Docling:** the earlier pipeline's table model (TableFormer), which guesses the table's grid from the picture.
- **Geometry (ours):**
  1. Find the header row by its column names.
  2. Note where each header sits across the page.
  3. Put every word under the header it sits closest to.
  4. Because one table row can wrap onto several printed lines (a price printed "USD" on one line and
     "12,000.00" on the next), every row is built around the one line that holds its Amount, and nearby lines
     join it.

### T3. Rules both methods share (so the comparison is fair)

- **"Ext. Price" is the line amount.** The 2016 and 2017 forms call the Amount column "Ext. Price" (extended
  price); it is not the unit price.
- **Flat fees:** a row with no quantity passes the row check when Price = Amount.
- **Misread currency:** a price is read even when OCR misreads the currency ("USE 12,000.00", "USO 23.00").

### T4. Re-read a single cell when it comes out empty

OCR on a whole page tends to skip a lone character, such as the "1" in a Qty cell. Cut out on its own, the cell
usually reads fine. So when a quantity or price comes out empty on a scanned page, we cut out just that cell and
try three readers in order, keeping the first that gives a number:
1. Apple Vision on the enlarged cell.
2. Apple Vision with a white margin added around the cell.
3. Tesseract reading one character, digits only.

All 6 empty quantity cells were recovered. Every re-read is written in the `reread` column of
`outputs/tables/pricing_rows_geometry_vision.csv`.

**Caveat:** this order was chosen while looking at those same 6 cells.

### T5. Which OCR to use for tables: Apple Vision

| Table reader | OCR on scanned pages | Row checks | Subtotals | Grand totals | Product rows found |
|---|---|---|---|---|---|
| Docling | earlier pipeline | 78/86 | 60/60 | 7/8 | 86 |
| Geometry | Tesseract | 19/20 | 13/13 | 4/4 | **20** |
| Geometry | Tesseract + Vision | 60/67 | 37/40 | 7/11 | 67 |
| Geometry | Vision, no cell re-read | 81/88 | 63/63 | 12/12 | 88 (6 with no Qty) |
| **Geometry** | **Vision + cell re-read** | **81/88** | **63/63** | **12/12** | **88 (0 with no Qty)** |

Table header rows sit on grey shading. Tesseract can't read text on grey, so it never finds most headers and
misses whole tables. That is why the best reading for paragraphs (R7) is not the best for tables: each kind of
content uses the reading that scored best on the test built for it.

### T6. The 7 rows that still fail are errors in the contracts themselves

We looked at the page picture for every failing row. In all 7, the printed numbers really do not multiply out:
- 400 users × $7,500.00 printed as $7,500 (F01),
- 1,000 users × $1,000.00 printed as $1,000 (three times in F02, once in F03),
- 425 users × $5,040.50 printed as $5,040.50 (F07),
- 500 users × $1.35 printed as $672.95 (F05, probably a part-year price).

Here the Price column holds a flat price or a rounded unit price. No reading method could make these rows pass,
so the reader has 0 known errors on the 88 product rows. The check does **not** test descriptions or dates; those
need a hand check.

---

## Order-form fields (F)

### F1. Eight fields from each of the 14 order forms

The fields: order number, order date, customer, billing frequency, payment terms, grand total, and the name and
signing date of the person who signed for the customer. They are the "who, when, how much" of each contract, and
later steps need them to tell the contracts apart.

The 14 order forms are listed in `data/order_forms.csv`. F11 holds two forms; F09, the California agreement, has
none.

**Answer key 2b** (`data/gold/order_form_fields.csv`) has 112 answers, typed from the page pictures:
- **99 are on the page.**
- **13 are not.** 11 are blacked out in the files we received; 2 are billing frequency on the 2016–2017 forms,
  which have no such field.

A method should leave those 13 empty, and a value it reports there counts as **invented**. The key includes three
deliberate traps:
- **Decoy order numbers.** F05 and F08 mention an *earlier* order's number ("supersedes … Q-35152-2"), and F05's
  own number is blacked out.
- **A crossed-out name.** On OF13 the typed signer name is crossed out and the real one is handwritten beside it.
- **Handwriting.** 3 names and 4 dates are handwritten.

**⚠ Still to do:** like answer key 1, it needs a person to check it.

### F2. Two methods, reading the same text

- **Text rules:**
  1. Join the page's text into one running string, as if read aloud top to bottom.
  2. Look for each label ("Order #:", "Payment Terms:").
  3. Take what follows it.

  Easy to write and to read. But running text loses the page's columns: two signature boxes side by side become
  one line.
- **Layout:**
  1. Find each label *on the page*.
  2. Take the words printed to its right on the same line, or on the nearest line just above or below.
  3. In the signature area, use the left box, because that is the customer's.

  This keeps columns apart. But it cannot find a value buried inside a paragraph.

Both read exactly the same text (R7 for words; T5 for money), so any difference comes from the method.

### F3. Results: layout is more accurate, mainly on signatures

| Field | Text rules | Layout |
|---|---|---|
| order number (12 on the page) | 12 | 12 |
| order date (14) | 14 | 14 |
| customer (14) | 12 | 12 |
| billing frequency (12) | 12 | 12 |
| payment terms (14) | **14** | 12 |
| grand total (14) | 14 | 14 |
| signer's name (9) | 3 | **6** |
| signing date (10) | 3 | **7** |
| **all 99 values** | **84 (84.8%), 1 invented** | **89 (89.9%), 0 invented** |

- **Decoy order numbers:** neither method was fooled. Both look for the number next to its label on the form's
  first page, so they never reach the decoys.
- **Text rules win on payment terms.** On the 2016–2017 forms, "Net 30" is buried inside a paragraph, where only a
  text search can find it.
- **Layout wins on signatures,** because it keeps the customer's box apart from Instructure's.
- **Handwriting stops both methods** (3 names, 2 dates). Fixing that needs a stronger reader (for example a vision
  language model on the lab server), not better rules.

**How the scores got here.** The first versions scored 76.8% (text rules) and 61.6% (layout). The fixes, each a
general rule rather than a patch for one form:
1. Drop DocuSign's hidden text (R1).
2. Read money with the table reading (T5).
3. Look far enough right for header values that sit in their own column.
4. Skip the heading "Customer Information" when looking for "Customer".
5. Look on the nearest line above as well as below.

They were found by looking at failures on these same 14 forms, so the final scores are development scores (as in
T6). The fairest test is order forms neither method has seen.

### F4. Comparing the two on the supervisor's criteria

| | Text rules | Layout |
|---|---|---|
| Manual work | low: one pattern per field | medium: labels plus rules about where values sit |
| Interpretability | high: each pattern can be read | high: each answer can be traced to a spot on the page |
| Consistency across document types | breaks when columns or reading order change | breaks when a value is inside a paragraph |
| Cost | none; seconds on a laptop | none; seconds on a laptop |
| Weak spot | side-by-side boxes (signatures) | values inside sentences (old payment terms) |

The two fail in different places, so a combination (layout first, text rules for fields layout leaves empty)
would likely beat both. We have not tested that yet.

---

## Server (S)

### S1. What runs where

- **Mac only:** Apple Vision. Its readings of all 156 pages, and of every re-read table cell, are saved and travel
  in the bundle, so the server reuses them and never needs Vision.
- **On the lab server:** RapidOCR's remaining 76 digital pages, the OCR scoring and the table step.
- **Reproducibility note:** anyone without a Mac can rerun every step after the Vision reading, but not the Vision
  reading itself.
