"""Entry point. Usage: python run.py <step> [<step> ...]

Steps, in order:
  read         render pages, record the PDF text layer, run the three OCR engines   (bench/reading.py)
  ocr-sample   pick lines from scanned pages for the hand-checked OCR answer key     (bench/ocr_eval.py)
  ocr-eval     score every reading against the answer keys                           (bench/ocr_eval.py)
  tables       read the pricing tables two ways and check them with arithmetic       (bench/tables.py)
"""
import sys

from bench import ocr_eval, reading, tables

STEPS = {
    "read": reading.main,
    "ocr-sample": ocr_eval.sample,
    "ocr-eval": ocr_eval.evaluate,
    "tables": tables.main,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or any(s not in STEPS for s in sys.argv[1:]):
        print(__doc__)
        sys.exit(1)
    for step in sys.argv[1:]:
        print(f"== {step}")
        STEPS[step]()
