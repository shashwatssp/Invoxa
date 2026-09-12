"""PDF statement export.

Renders the invoices of one account as a clean, printable A4 statement
using PyMuPDF (already a dependency -- the receipt preview uses it on
Vercel), so no new packages are introduced.

Design decisions (see docs/plans/product-roadmap.local.md, decision D3):
- Amounts are rendered as ``Rs 1,23,456.00`` with Indian digit grouping
  because PyMuPDF's bundled base-14 fonts have no rupee glyph.
- Pagination is manual: a fixed number of rows per page, the table header
  repeats on every page, and every page footer carries running totals.
- An empty selection still produces a valid one-page PDF saying so.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

import pymupdf

# A4 in points; 15mm margins (~42.52pt).
PAGE_W, PAGE_H = 595.0, 842.0
MARGIN = 42.5
ROWS_PER_PAGE = 26
ROW_HEIGHT = 18.0

# Fixed column layout (left edges; totals are right-aligned to these edges).
COL_DATE = MARGIN
COL_NUMBER = MARGIN + 78
COL_VENDOR = MARGIN + 178
COL_TOTAL_RIGHT = PAGE_W - MARGIN  # right-aligned edge of the Total column

FONT = "helv"
FONT_BOLD = "hebo"


def _amount(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _inr(value: Any) -> str:
    """Render an amount as ``Rs 1,23,456.00`` with Indian digit grouping."""
    text = f"{_amount(value):.2f}"
    whole, _, frac = text.partition(".")
    sign = ""
    if whole.startswith("-"):
        sign, whole = "-", whole[1:]
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}Rs {whole}.{frac}"


def _fmt_date(value: Any) -> str:
    """Render created_at as ``DD Mon YYYY`` for the statement rows."""
    if not value:
        return "-"
    raw = str(value)
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:10]
    return parsed.strftime("%d %b %Y")


def _truncate(text: str, width: float, fontsize: float) -> str:
    """Clip a string (with an ellipsis) so it fits the column width."""
    if pymupdf.get_text_length(text, fontname=FONT, fontsize=fontsize) <= width:
        return text
    while text and pymupdf.get_text_length(
        text + "…", fontname=FONT, fontsize=fontsize
    ) > width:
        text = text[:-1]
    return text + "…"


def build_pdf_statement(
    rows: list[dict[str, Any]],
    *,
    period_label: str,
    owner_email: str = "",
    generated_at: dt.datetime | None = None,
) -> bytes:
    """Render invoice rows as an A4 statement PDF. Never raises on empty input."""
    generated_at = generated_at or dt.datetime.now(dt.UTC)
    rows = sorted(rows, key=lambda r: str(r.get("created_at") or ""))
    grand_total = sum(_amount(r.get("amount")) for r in rows)

    doc = pymupdf.open()
    total_pages = max(1, math.ceil(len(rows) / ROWS_PER_PAGE))

    for page_index in range(total_pages):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        first_on_page = page_index * ROWS_PER_PAGE
        page_rows = rows[first_on_page : first_on_page + ROWS_PER_PAGE]

        # -- Header (title block on the first page only) ----------------
        y = MARGIN + 16
        if page_index == 0:
            page.insert_text(
                (MARGIN, y), "Invoxa — Invoice Statement",
                fontname=FONT_BOLD, fontsize=15,
            )
            y += 16
            subline = " · ".join(
                part for part in (owner_email, period_label,
                                  f"Generated {generated_at.strftime('%d %b %Y %H:%M')}")
                if part
            )
            page.insert_text((MARGIN, y), subline, fontname=FONT, fontsize=8.5,
                             color=(0.35, 0.4, 0.48))
            y += 14

        # -- Table header (repeats on every page) ------------------------
        header_y = max(y, MARGIN + 16) + 10
        header = [
            (COL_DATE, "Date", False),
            (COL_NUMBER, "Invoice #", False),
            (COL_VENDOR, "Vendor", False),
            (COL_TOTAL_RIGHT, "Total", True),
        ]
        for x, label, right in header:
            if right:
                width = pymupdf.get_text_length(label, fontname=FONT_BOLD, fontsize=8.5)
                page.insert_text((x - width, header_y), label,
                                 fontname=FONT_BOLD, fontsize=8.5)
            else:
                page.insert_text((x, header_y), label, fontname=FONT_BOLD, fontsize=8.5)
        page.draw_line(
            (MARGIN, header_y + 5), (PAGE_W - MARGIN, header_y + 5),
            color=(0.55, 0.58, 0.64), width=0.7,
        )

        # -- Rows ---------------------------------------------------------
        row_y = header_y + ROW_HEIGHT
        for i, row in enumerate(page_rows):
            if i % 2 == 1:
                page.draw_rect(
                    pymupdf.Rect(
                        MARGIN, row_y - ROW_HEIGHT + 4,
                        PAGE_W - MARGIN, row_y + 4,
                    ),
                    color=None, fill=(0.94, 0.95, 0.97),
                )
            vendor = str(row.get("vendor_name") or row.get("vendor_id") or "-")
            cells = [
                (COL_DATE, _fmt_date(row.get("created_at")), False),
                (COL_NUMBER, str(row.get("invoice_number") or "-"), False),
                (COL_VENDOR, vendor, False),
                (COL_TOTAL_RIGHT, _inr(row.get("amount")), True),
            ]
            for x, text, right in cells:
                if right:
                    width = COL_TOTAL_RIGHT - COL_VENDOR - 10
                    rendered = _truncate(text, width, 8.5)
                    tw = pymupdf.get_text_length(rendered, fontname=FONT, fontsize=8.5)
                    page.insert_text((x - tw, row_y), rendered, fontname=FONT, fontsize=8.5)
                else:
                    col_width = {
                        COL_DATE: COL_NUMBER - COL_DATE - 5,
                        COL_NUMBER: COL_VENDOR - COL_NUMBER - 5,
                        COL_VENDOR: COL_TOTAL_RIGHT - COL_VENDOR - 10,
                    }[x]
                    page.insert_text(
                        (x, row_y), _truncate(text, col_width, 8.5),
                        fontname=FONT, fontsize=8.5,
                    )
            row_y += ROW_HEIGHT

        # -- Footer -------------------------------------------------------
        if not rows and page_index == 0:
            page.insert_text(
                (MARGIN, header_y + 40), "No invoices in this period.",
                fontname=FONT, fontsize=10, color=(0.35, 0.4, 0.48),
            )
        footer = (
            f"Page {page_index + 1} of {total_pages} · "
            f"{len(rows)} invoice{'s' if len(rows) != 1 else ''} · Total {_inr(grand_total)}"
        )
        fw = pymupdf.get_text_length(footer, fontname=FONT, fontsize=8)
        page.insert_text(((PAGE_W - fw) / 2, PAGE_H - 24), footer,
                         fontname=FONT, fontsize=8, color=(0.35, 0.4, 0.48))

    return doc.write()
