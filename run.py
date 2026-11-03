"""Entry point. Usage: python run.py <step> [<step> ...]

Steps, in order:
  read         render pages, record the PDF text layer, run the three OCR engines   (bench/reading.py)
  ocr-sample   pick lines from scanned pages for the hand-checked OCR answer key     (bench/ocr_eval.py)
  ocr-eval     score every reading against the answer keys                           (bench/ocr_eval.py)
  tables       read the pricing tables two ways and check them with arithmetic       (bench/tables.py)
  forms        read 8 fields from each order form two ways and score them             (bench/forms.py)
  text         turn printed lines into clean whole text: no page furniture, whole       (bench/text.py)
               paragraphs across lines and pages, table and form rows kept together
  privacy      find data-governance-and-privacy passages; score on the tuning files  (bench/privacy.py)
  privacy-test the same on the test files; run once, after everything is frozen
  privacy-embed  (server) meaning vectors for every block                            (bench/privacy_server.py)
  privacy-llm    (server) Llama marks section starts and answers yes or no           (bench/privacy_server.py)
"""
import sys

from bench import forms, ocr_eval, privacy, reading, tables, text

STEPS = {
    "read": reading.main,
    "ocr-sample": ocr_eval.sample,
    "ocr-eval": ocr_eval.evaluate,
    "tables": tables.main,
    "forms": forms.main,
    "text": text.main,
    "privacy": privacy.main,
    "privacy-test": privacy.main_test,
    "privacy-embed": lambda: __import__("bench.privacy_server", fromlist=["x"]).embed(),
    "privacy-llm": lambda: __import__("bench.privacy_server", fromlist=["x"]).llm(),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or any(s not in STEPS for s in sys.argv[1:]):
        print(__doc__)
        sys.exit(1)
    for step in sys.argv[1:]:
        print(f"== {step}")
        STEPS[step]()
