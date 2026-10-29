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

## Order-form fields

**16. Hidden DocuSign text garbled every signature on the DocuSign forms.**
- **What happened:** the stored text of five order forms (OF07, OF11a, OF11b, OF12, OF14) holds invisible white
  tags on top of the visible names. "Jessie Combs" came out as "J\ecslmsie-n C1o\ mbs", and "Anne Barnes" as just
  "\n1\". Both methods failed on all five.
- **Fix:** hidden text is now dropped when the stored text is read (R1).

**17. The first fix for hidden text also deleted visible text.**
- **What happened:** dropping *all* white characters removed "Billing Summary" from F14, because it is printed
  white on a blue bar. The F14 grand total then disappeared for text rules.
- **Fix:** only white text with nothing coloured behind it is dropped now, and the dropped characters were checked
  by hand: all tags.
- **Lesson:** a fix needs its own check.

**18. The first versions of both methods.**
- **Scores:** text rules 76.8%; layout 61.6%.
- **Layout's main slip:** in the header, the values stand in their own column far to the right. Layout looked only
  a short distance right, found nothing, then took the next line down, which is the "Offer Valid Through" date.
  Only 4 of 14 order dates were right.
- **Both methods' slip:** they took the section heading "Customer Information" for the customer's name. (F3)

**19. Text rules can't keep two columns apart.**
- **What happened:** running text puts the customer's and Instructure's signature boxes on one line, so the signer
  came out as "Angela Fredrickson Elizabeth Powe…".
- **Second problem:** when a typed name sits slightly above its label, the running text puts it before the label,
  so the rule took the Title instead ("Vice Chancellor, Business & Finance").
- **Result:** 3 of 9 signer names. This is built into the method, so it was left as it is.

**20. Layout can't see a value inside a sentence.** On the 2016–2017 forms, the payment terms are a paragraph
("…Customer must pay such amount to Instructure Net 30 on the date of this order"). Layout looks for a value next
to the label, finds a sentence, and misses both. Text rules find "Net 30" in both.

**21. Handwriting.**
- **Names:** "Angela Fredrickson" came out as "Angelatredrideson", and "Paul Turman" as "Pavl Turman".
- **Crossed-out name:** on OF13 the crossed-out typed name came out as "chort Rotonate" beside the handwritten
  "Paul Turman".
- **Date:** "7/29/2016" came out as "7/21/2016".
- **What would help:** no rule fixes these; it needs a stronger reader. (F3)

## Clean text

**22. The text we had was printed lines, not usable text, and our tests could not see it.**
- **What I found:** checking answer key 1 (Oct 29), I found sentences cut off at line ends and never
  continued, page numbers mixed into the text, one-word rows like "Per Year" and "Customer.", and what looked like
  missing sentences.
- **Cause:** the key was built from single printed lines, so this is what it looks like. The pipeline's own text
  had the same problems.
- **Our mistake:** a line-by-line letter test can't detect any of this. We had good letter scores and unusable
  text, and we asked for the check without explaining what the rows were.
- **Fix:** step C now rebuilds whole text and counts each problem (decisions.md, C).

**23. The first clean text read pricing tables a second time.**
- **What happened:** with the paragraph reading, the grey-shaded table rows came out as "Recurring | Rn NRE | Jo
  AINSI", and product names were torn from their rows.
- **Fix:** tables now come from the arithmetic-checked table step (C2).

**24. Clause numbers deleted as page headers.** The rule for running headers removed "19.6", "19.7", "19.16" in F07,
because those clauses happened to start near the top of three pages. A repeated header now needs at least three
letters.

**25. A clean-up rule that deleted real content.** A rule to drop scraps (fewer than two letters or digits, or short
non-words) took removals from 8 to 216. It deleted:
- 33 quantities ("1"),
- 32 column headers ("Qty"),
- clause and section numbers ("1." to "9.", "A." to "E.").

Narrowed, it then still removed a tick mark (✔, a ticked tax-exempt box), a column header "Expiration" and part of
a handwritten phone number. Now anything with a real word, a 3+ digit number or a tick is kept. Lesson: when unsure,
keep the text; a scrap is a small cost, a lost quantity is not.

**26. Unsure OCR that was real.** Of 23 lines Tesseract was unsure of (under 50%) and Apple Vision did not read, 20
were garbage. But one was the end of a real sentence ("Customer's instructions.", 48% sure) and one a lone "1". The
rule now also needs the line to be mostly non-words with no digits; 16 lines go.

**27. Two paragraph rules that cut sentences.**
- **"(ii)" read as a new item:** clause 2 of F02 was cut in half at "(ii) harm or impersonate…", because an item
  marker at a line start was taken as a new paragraph even mid-sentence.
- **Clause 10 not joined across pages:** its ALL-CAPS sentence wasn't joined across the page break, because the
  check for capitals looked at the whole paragraph, whose heading is not in capitals.

**28. The missing-text check confused misspellings with missing lines.**
- **What it reported:** "either … sixty … contractor" missing on F13 p2.
- **What was really there:** the lines were there, read as "eilher … sixly … Conlractor".
- **Fix:** the check now tells "line missing" (3) from "word misread" (30) (C5).

**29. A fix that made no difference.** A dictionary vote between Tesseract and Apple Vision changed 43 lines and
none of the scores (decisions.md, R8). It was not adopted.

**30. Keeping anything with a digit kept garbage.** "5 eis =", "£5" and "3% Ci" were kept because a digit might be
a quantity. I confirmed they are not on the page. Lines Tesseract is under 30% sure of, which Vision does not
confirm, now go regardless (decisions.md, C7).

**31. "Empty" rules that removed content.** The first rule for empty fields removed:
- labels whose content is printed below them ("Metrics and Descriptions:", "Supplier Name:"),
- a list's lead-in,
- the title "ACCEPTED BY:".

The first rule for empty sections removed:
- two signers' titles,
- a "Source:" link,
- the label "Title:" (twice).

And it missed "Notes", the one it was written for, because it asked for a fifth of the page blank and "Notes" has
14%. Both rules are now narrow (C7). Found by listing every removal across all 14 files before showing the result.

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

**14. The first real server run crashed anyway.**
- **What happened:** the code read an English word list from `/usr/share/dict/words`, which every Mac has and the
  lab server does not. The simulated test ran on the Mac, so it could not catch this.
- **Fix:** the same list now ships inside the project (`data/english_words.txt.gz`), so every computer uses
  exactly the same words.
- **Lesson:** a pretend server on a Mac is not a server.

**15. The "is this real text?" check was too lenient.**
- **What happened:** to forgive plurals and such, it trimmed up to three letters off a word before looking it up.
  Trimming "xqzt" left "x", which counts as a word, so nonsense passed.
- **Fix:** it now trims only real endings (-s, -es, -ed, -ing, -ly).
- **Side effect:** clean order forms now score about 80% (their names and product words aren't in the
  dictionary), so the cut-off for answer key 2 was lowered from 85% to 70%. No page falls between the two.
