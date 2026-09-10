"""Extraction accuracy harness.

Runs the extraction pipeline directly (no server) over every PDF in
backend/test-assets and prints a per-field matrix with confidences and
verdicts. Used to iterate on the algorithm until targets are met.

Run:  python scripts/extraction_harness.py
"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\Shashwat S Pandey\Invoxa\backend")

from app.extraction.pipeline import extract_from_invoice  # noqa: E402
from app.extraction.regex_rules import extract_all_fields  # noqa: E402
from app.validation.anomaly import detect_anomalies  # noqa: E402
from app.validation.duplicate import is_duplicate  # noqa: E402

ASSETS = Path(r"C:\Users\Shashwat S Pandey\Invoxa\backend\test-assets")

GROUND_TRUTH = {
    "gst_invoice_a.pdf": {
        "vendor_gstin": "29AABCS1429B1ZD",
        "invoice_number": "INV-2026-0901",
        "total_amount": 46551.00,
        "tax_amount": 7101.00,
    },
    "gst_invoice_b.pdf": {
        "vendor_gstin": "33AAKCK8392M1Z7",
        "invoice_number": "CL/FY27/0442",
        "total_amount": 15930.00,
        "tax_amount": 2430.00,
    },
}

# Documents that should AUTO-APPROVE (clean text, sane data present).
SHOULD_AUTO_APPROVE = {
    "gst_invoice_a.pdf",
    "gst_invoice_b.pdf",
    "azure_invoice.pdf",
    "fr_rest_api_invoice.pdf",
    "flight_invoice_2p.pdf",
    "weird_invoice.pdf",
}


def main() -> int:
    pdfs = sorted(ASSETS.rglob("*.pdf"))
    failures = 0

    for pdf in pdfs:
        name = pdf.name
        data = pdf.read_bytes()
        result = extract_from_invoice(data, "harness")
        print(f"\n=== {name} ===")
        print(
            f"  vendor={result.vendor_name!r} gstin={result.vendor_gstin!r} "
            f"number={result.invoice_number!r}"
        )
        print(
            f"  dates={result.invoice_date!r}/{result.due_date!r} "
            f"subtotal={result.amount!r} tax={result.tax_amount!r} "
            f"total={result.total_amount!r}"
        )
        print(
            f"  overall={result.overall_confidence} "
            f"needs_review={result.needs_review}"
        )
        fields = extract_all_fields(result.raw_text or "")
        gst_applicable = bool(fields["gstin_candidates"]) or fields["has_gst_keywords"]
        anomalies = detect_anomalies(result, gstin_applicable=gst_applicable)
        dup = is_duplicate(result.vendor_gstin, result.invoice_number, result.total_amount)
        print(f"  anomalies={anomalies} duplicate={dup}")

        expected = GROUND_TRUTH.get(name)
        if expected:
            checks = {
                "vendor_gstin": result.vendor_gstin == expected["vendor_gstin"],
                "invoice_number": result.invoice_number == expected["invoice_number"],
                "total_amount": result.total_amount is not None
                and abs(result.total_amount - expected["total_amount"]) < 0.01,
                "tax_amount": result.tax_amount is not None
                and abs(result.tax_amount - expected["tax_amount"]) < 0.01,
            }
            for check, ok in checks.items():
                print(f"  {'PASS' if ok else 'FAIL'}: {check}")
                if not ok:
                    failures += 1

        want_auto = name in SHOULD_AUTO_APPROVE
        if want_auto and result.needs_review:
            print("  FAIL: expected AUTO-APPROVE, got flagged")
            failures += 1
        if not want_auto and not result.needs_review:
            print("  FAIL: expected flagged, got auto-approved")
            failures += 1

    print(f"\nRESULT: {'ALL TARGETS MET' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
