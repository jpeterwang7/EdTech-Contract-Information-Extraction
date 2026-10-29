# What failed

Things we tried that did not work, or worked worse than expected, with the numbers and an example of each.
The supervisor asked to see failures as well as successes; each one also changed a decision in
[decisions.md](decisions.md).

## Reading the pages

**1. The earlier pipeline's OCR (Docling + RapidOCR at 216 dpi).**
- **Scores:** 8.8% of characters wrong; 61% of numbers exact.
- **Example:** on the 2016 terms (F01 p3), section 8's heading and first words came out as "Cos (s o o ot …". That
  section is the one holding the data-safeguards sentence.
- **Cause:** the same engine (RapidOCR) at 300 dpi gets 98% of numbers right, so the setup around the engine
  failed, not the engine itself. (R6)

**2. Trusting Apple Vision after one good page.** It read the 2016 terms page almost perfectly, so we first planned
to use it everywhere. The systematic test changed that:
- **Silent skipping:** Vision skips whole blocks of text without any warning. On F03 p3 it returned 244 words
  where Tesseract found 422, and the missing half included a deliverables cell. On F13 p3 it skipped a paragraph
  ("…shall be void and of no effect…").
- **Lesson:** one good-looking page is not evidence. (R6, R7)

**3. RapidOCR at 300 dpi on dense paragraphs.**
- **Score:** 5.1% of characters wrong.
- **Example:** "document. Customer shall not assign…" came out as "do t t it t tto t t t to assign…" (F02 p7). (R6)

**4. Tesseract on shaded or coloured backgrounds.**
- **Headings:** "TAX INFORMATION" on grey was read as nothing useful, and "June 2022" (white on red) as blank.
- **Tables:** worse, because table header rows are shaded. With Tesseract the table reader found only 20 of the
  88 product rows. (R6, T5)

**5. Using the paragraph-text winner for tables.** The Tesseract + Vision combination, best for paragraphs, made
tables worse:
- **Scores:** 67 product rows instead of 88; grand totals added up in 7 of 11 order forms instead of 12 of 12.
- **Example:** Tesseract read "155,674.61" as "165,674.61" in an F10 table (the subtotal check caught it). (T5)

## Pricing tables

**6. Our first table reader.**
- **Design:** one printed line = one table row; header words matched one by one.
- **Score:** it passed only 55 of 87 row checks (63%), *worse* than Docling (71% at that time).
- **Causes:**
  - "Ext." and "Price" were read as two separate columns in the 2016–2017 forms.
  - Prices printed on two lines ("USD" / "12,000.00") were cut in half.
- **Fix:** both were fixed (T2, T3). Docling also gained from the shared fixes, so the comparison stays fair.

**7. Lone characters disappear.**
- **What happened:** whole-page OCR left the Qty cell empty in 6 rows, though each clearly shows "1". Both Apple
  Vision and Tesseract missed the same cell in F06, and Vision read "USD" as "USE" with full confidence.
- **Why it's dangerous:** these rows still *passed* the arithmetic check under the flat-fee rule. An incomplete row
  looked correct.
- **Fixes:**
  - Rows with no quantity are now counted separately.
  - Empty cells are re-read one at a time (T4), which recovered 6 of 6.
- **Caveat:** the re-read order was tuned on those 6 cells.

**8. Docling's tables.**
- **Missing rows:** it missed the whole Year 5 block and the Grand Total in F03.
- **Number misreads:** "3,292" became "3,202", and "USD" became "USO" / "US0".
- **Merged rows:** in F04 it merged the Year 3 Total and the Grand Total into one cell.
- **Misspelled descriptions:** "Camvas", "Carvas", "Besic Support", "CloudSubsoription".

**9. What the arithmetic check cannot see.**
- **Not checked:** descriptions and dates are not tested at all.
- **Errors in the source:** 7 rows fail because the contracts' own numbers don't multiply out (T6). A reader can't
  "fix" those, and they set a ceiling on the row-check score.

## The tests themselves

**10. The digital-page answer key had invisible text in it.**
- **Symptom:** every engine got only about 65% of numbers "exact" on clean digital pages, worse than on scans.
- **Cause:** the stored text includes things nobody can see on the page: coded characters ("(cid:182)"),
  DocuSign's hidden tags ("\s1\"), and table-of-contents dot leaders.
- **Fix:** those 39 lines (of 3,335) are now left out. (R5)

**11. No untouched test set for the table reader.** Its design was improved by looking at failures on the same
14 files it is scored on. The 81/88, 63/63, 12/12 results are development scores. The honest test is new contracts
the reader has never seen.

## Running the work

**12. A crash left a half-written file.** The OCR run stopped on a number-format error halfway through writing a
result. On restart, the half-written file looked "done". The fix: every result is now written to a temporary
file and renamed only when complete.

**13. The server bundle crashed in testing.** In a simulated server run, the table step crashed when Tesseract was
installed but its English model was not. This was caught and fixed before upload.
