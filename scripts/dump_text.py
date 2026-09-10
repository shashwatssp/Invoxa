"""Dump the text layer of specific test PDFs to inspect labels."""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\Shashwat S Pandey\Invoxa\backend")
from app.extraction.ocr import extract_text  # noqa: E402

ASSETS = Path(r"C:\Users\Shashwat S Pandey\Invoxa\backend\test-assets")
OUT = Path(r"C:\Users\Shashwat S Pandey\Invoxa\scripts\text_dump.txt")

with OUT.open("w", encoding="utf-8") as out:
    for name in [
        r"remote\azure_invoice.pdf",
        r"remote\weird_invoice.pdf",
        r"remote\flight_invoice_2p.pdf",
        r"remote\azure_gpt4v_invoice_1.pdf",
        "gst_invoice_a.pdf",
        "gst_invoice_b.pdf",
    ]:
        text, used_ocr = extract_text((ASSETS / name).read_bytes())
        out.write(f"\n\n########## {name} (ocr={used_ocr}) ##########\n")
        out.write(text[:2200])

print("dumped")
