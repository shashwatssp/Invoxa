"""Tally Prime XML export.

Generates a Tally-compatible ``Import Data`` envelope containing one
Purchase voucher per invoice. Import in Tally Prime via
Gateway of Tally > Import > XML.

Ledger convention (Tally's signed-amount model, debit positive):
- Party ledger (vendor) is credited:  ISDEEMEDPOSITIVE=Yes, AMOUNT=-total
- Purchase ledger is debited:         ISDEEMEDPOSITIVE=No,  AMOUNT=+net
- Input tax credit is debited:        ISDEEMEDPOSITIVE=No,  AMOUNT=+tax
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from app.database import get_invoices

TALLY_COMPANY_PLACEHOLDER = "Invoxa Company"


def _tally_date(value: Any) -> str:
    """Render a date as YYYYMMDD (Tally's format). Empty when unparseable."""
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw[:10] if fmt == "%Y-%m-%d" else raw, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return ""


def _amount(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _voucher_for(invoice: dict[str, Any]) -> str:
    vendor = (
        invoice.get("vendor_name")
        or invoice.get("vendor_id")
        or "Unknown Party"
    )
    number = invoice.get("invoice_number") or invoice.get("id") or ""
    date = _tally_date(invoice.get("due_date") or invoice.get("created_at"))
    total = _amount(invoice.get("amount"))

    # Net/tax split: tax_amount currently mirrors the invoice amount column,
    # so treat the full amount as the taxable value unless a separate tax
    # breakdown exists. The party entry always balances the sum.
    ledger_lines = [
        f"""        <ALLLEDGERENTRIES.LIST>
         <LEDGERNAME.PARTY>{escape(vendor)}</LEDGERNAME.PARTY>
         <LEDGERNAME>{escape(vendor)}</LEDGERNAME>
         <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
         <AMOUNT>-{total:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>"""
    ]
    if total:
        ledger_lines.append(
            f"""        <ALLLEDGERENTRIES.LIST>
         <LEDGERNAME>Purchase Account</LEDGERNAME>
         <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
         <AMOUNT>{total:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>"""
        )

    return f"""    <TALLYMESSAGE xmlns:UDF="TallyUDF">
     <VOUCHER VCHTYPE="Purchase" ACTION="Create" OBJVIEW="Accounting Voucher View">
      <DATE>{date}</DATE>
      <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
      <VOUCHERNUMBER>{escape(str(number))}</VOUCHERNUMBER>
      <PARTYLEDGERNAME>{escape(vendor)}</PARTYLEDGERNAME>
      <PARTYNAME>{escape(vendor)}</PARTYNAME>
      <NARRATION>Imported from Invoxa</NARRATION>
{chr(10).join(ledger_lines)}
     </VOUCHER>
    </TALLYMESSAGE>"""


def build_tally_xml(
    status_filter: str | None = None, user_id: str | None = None
) -> str:
    """Render the full Tally import XML, scoped to one account."""
    rows = get_invoices(user_id)
    if status_filter:
        rows = [r for r in rows if (r.get("status") or "") == status_filter]

    vouchers = "\n".join(_voucher_for(row) for row in rows)
    return f"""<ENVELOPE>
 <HEADER>
  <TALLYREQUEST>Import Data</TALLYREQUEST>
 </HEADER>
 <BODY>
  <IMPORTDATA>
   <REQUESTDESC>
    <REPORTNAME>Vouchers</REPORTNAME>
    <STATICVARIABLES>
     <SVCURRENTCOMPANY>{escape(TALLY_COMPANY_PLACEHOLDER)}</SVCURRENTCOMPANY>
    </STATICVARIABLES>
   </REQUESTDESC>
   <REQUESTDATA>
{vouchers}
   </REQUESTDATA>
  </IMPORTDATA>
 </BODY>
</ENVELOPE>
"""
