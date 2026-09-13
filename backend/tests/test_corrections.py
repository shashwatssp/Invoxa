"""
Unit tests for the review corrections module.

Uses a tiny in-memory fake Supabase client so the tests stay
DB-agnostic. The fake supports the same fluent query shape as the real
supabase-py client: ``table(...).select(...).eq(...).single()/limit(...)``.
Insertions and updates are recorded on the fake so tests can assert them.
"""
import pytest
from app.models.invoice import Correction
from app.review import corrections
from app.review.corrections import (
    apply_correction_to_invoice,
    has_pending_review,
    log_correction,
)


class FakeTable:
    """A queryable in-memory collection.

    Each instance pins to a backing list the FakeClient owns, so data
    inserted via one table reference can be queried back through another.
    Tests can also seed rows through ``extend`` or index via ``[]`` for
    convenience.
    """

    def __init__(self, name, store):
        self._name = name
        self._store = store
        self._filters: list[tuple[str, str]] = []

    def select(self, *_fields, **kwargs):
        self._selecting = True
        self._limit = None
        self._single = False
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        # Mirror real supabase-py: ``single()`` is a marker that the next
        # ``execute()`` will return a single row rather than a list.  Returning
        # ``self`` keeps the fluent chain intact and lets the production code
        # call ``.execute()`` once.
        self._single = True
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload):
        self._update = payload
        return self

    def execute(self):
        if hasattr(self, "_insert"):
            payload = self._insert
            self._insert = None
            new_row = dict(payload)
            new_row["id"] = f"{self._name}-{len(self._store) + 1}"
            if self._name == "corrections":
                new_row.setdefault("corrected_at", "2026-09-02T00:00:00+00:00")
            self._store.append(new_row)
            return _response([new_row])

        if hasattr(self, "_update"):
            payload = self._update
            self._update = None
            matched = self._materialize()
            for row in matched:
                row.update(payload)
            return _response([dict(r) for r in matched])

        if getattr(self, "_selecting", False):
            rows = self._materialize()
            if getattr(self, "_single", False):
                return _response(rows[0] if rows else None)
            limit = getattr(self, "_limit", None)
            if limit is not None:
                rows = rows[:limit]
            # Hand back copies so the read API stays read-only in tests.
            return _response([dict(r) for r in rows])
        return _response([])

    def _materialize(self):
        # Return row *references* so that ``.update()`` mutates the backing
        # store in place (the read path wraps results in copies before
        # yielding them, so reads stay read-only while writes persist).
        return [
            row
            for row in self._store
            if all(row.get(col) == val for col, val in self._filters)
        ]

    # The next six hooks are test-only conveniences. They proxy the
    # underlying backing list so tests can seed/inspect rows directly.
    def extend(self, rows):
        self._store.extend(rows)
        return self

    def append(self, row):
        self._store.append(row)
        return self

    def __getitem__(self, idx):
        return self._store[idx]

    def __setitem__(self, idx, value):
        self._store[idx] = value

    def __len__(self):
        return len(self._store)

    def __iter__(self):
        return iter(self._store)


class FakeClient:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}

    def table(self, name: str):
        self.tables.setdefault(name, [])
        return FakeTable(name, self.tables[name])


class _Response:
    def __init__(self, data):
        self.data = data


def _response(data):
    return _Response(data)


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient()

    monkeypatch.setattr(corrections, "get_client", lambda: client)
    return client


def test_log_correction_happy_path(fake_client):
    fake_client.table("review_queue").extend([{
        "id": "rq-1", "invoice_id": "inv-1", "status": "pending",
    }])
    fake_client.table("extraction_fields").extend([{
        "id": "ef-1", "invoice_id": "inv-1", "field_name": "amount",
        "raw_value": "1000.00", "confidence": 0.7,
    }])

    correction = log_correction(
        review_id="rq-1",
        field_name="amount",
        new_value="1180.00",
    )

    assert isinstance(correction, Correction)
    assert correction.invoice_id == "inv-1"
    assert correction.field_name == "amount"
    assert correction.old_value == "1000.00"
    assert correction.new_value == "1180.00"
    # Verify the persist happened by reading from the backing store.
    assert fake_client.tables["corrections"]
    inserted = fake_client.tables["corrections"][0]
    assert inserted["old_value"] == "1000.00"
    assert inserted["new_value"] == "1180.00"


def test_log_correction_unknown_review_id(fake_client):
    with pytest.raises(LookupError):
        log_correction(review_id="missing", field_name="amount", new_value="100")


def test_log_correction_empty_inputs(fake_client):
    with pytest.raises(ValueError):
        log_correction(review_id="rq-1", field_name="", new_value="100")
    with pytest.raises(ValueError):
        log_correction(review_id="rq-1", field_name="amount", new_value="")
    with pytest.raises(ValueError):
        log_correction(review_id="rq-1", field_name="amount", new_value="   ")


def test_apply_correction_updates_existing_field(fake_client):
    fake_client.table("extraction_fields").extend([{
        "id": "ef-99", "invoice_id": "inv-9", "field_name": "vendor_gstin",
        "raw_value": "27OLDCHARACTERSX", "confidence": 0.6,
    }])
    correction = Correction(
        invoice_id="inv-9",
        field_name="vendor_gstin",
        old_value="27OLDCHARACTERSX",
        new_value="27NEWVALIDG0000Z5",
        corrected_at="2026-09-02T00:00:00+00:00",
    )
    apply_correction_to_invoice(correction)
    # Read directly from the backing store (the read API itself returns
    # copies, so assertions must bypass it to verify the write happened).
    updated = fake_client.tables["extraction_fields"][0]
    assert updated["raw_value"] == "27NEWVALIDG0000Z5"
    assert updated["confidence"] == 1.0


def test_apply_correction_inserts_when_missing(fake_client):
    correction = Correction(
        invoice_id="inv-77",
        field_name="invoice_number",
        old_value=None,
        new_value="INV-2026-009",
        corrected_at="2026-09-02T00:00:00+00:00",
    )
    apply_correction_to_invoice(correction)
    inserted = fake_client.tables["extraction_fields"][0]
    assert inserted["invoice_id"] == "inv-77"
    assert inserted["field_name"] == "invoice_number"
    assert inserted["raw_value"] == "INV-2026-009"
    assert inserted["confidence"] == 1.0


def test_has_pending_review(fake_client):
    fake_client.table("review_queue").extend([{
        "id": "rq-1", "invoice_id": "inv-1", "status": "pending",
    }])
    assert has_pending_review("rq-1") is True

    fake_client.table("review_queue")[0]["status"] = "approved"
    assert has_pending_review("rq-1") is False

    assert has_pending_review("not-present") is False


# ------------------------------------------------------------ normalization


def test_normalize_amount_strips_separators():
    assert corrections.normalize_value("amount", "1,180.50") == "1180.5"
    assert corrections.normalize_value("tax_amount", "1 250") == "1250.0"
    assert corrections.normalize_value("total_amount", "\u20b91180") == "1180.0"
    assert corrections.normalize_value("amount", " 42 ") == "42.0"


def test_normalize_dates_to_iso():
    assert corrections.normalize_value("due_date", "15/03/2026") == "2026-03-15"
    assert corrections.normalize_value("due_date", "15-03-2026") == "2026-03-15"
    assert corrections.normalize_value("due_date", "2026-03-15") == "2026-03-15"
    assert corrections.normalize_value("invoice_date", "01/01/2026") == "2026-01-01"


def test_normalize_passthrough_text_fields():
    assert corrections.normalize_value("invoice_number", "  INV-9 ") == "INV-9"


def test_normalize_rejects_garbage():
    with pytest.raises(ValueError):
        corrections.normalize_value("amount", "lots")
    with pytest.raises(ValueError):
        corrections.normalize_value("due_date", "sometime")


# ------------------------------------------------------- editable whitelist


def test_log_correction_rejects_unknown_field(fake_client):
    fake_client.table("review_queue").extend([{
        "id": "rq-2", "invoice_id": "inv-2", "status": "pending",
    }])
    with pytest.raises(ValueError, match="not editable"):
        log_correction(review_id="rq-2", field_name="vendor_name", new_value="Acme")


def test_invoice_level_fields_constant():
    assert {
        "invoice_number",
        "amount",
        "tax_amount",
        "total_amount",
        "due_date",
    } == corrections.INVOICE_LEVEL_FIELDS
    # The grand total lives in the canonical ``amount`` column.
    assert corrections.INVOICE_COLUMN_MAP["total_amount"] == "amount"


def test_apply_correction_patches_invoice_table(fake_client):
    # Correcting an invoice-level field should also update the invoices table.
    fake_client.table("invoices").extend([{
        "id": "inv-50",
        "invoice_number": "OLD-001",
        "amount": 1000.0,
        "due_date": "2026-01-01",
        "status": "flagged",
    }])
    correction = Correction(
        invoice_id="inv-50",
        field_name="invoice_number",
        old_value="OLD-001",
        new_value="NEW-999",
        corrected_at="2026-09-02T00:00:00+00:00",
    )
    apply_correction_to_invoice(correction)
    updated = fake_client.tables["invoices"][0]
    assert updated["invoice_number"] == "NEW-999"


def test_apply_correction_skips_invoice_table_for_non_invoice_field(fake_client):
    # Non-invoice-level fields should NOT touch the invoices table.
    fake_client.table("invoices").extend([{
        "id": "inv-51",
        "vendor_name": "OldVendor",
    }])
    correction = Correction(
        invoice_id="inv-51",
        field_name="vendor_gstin",
        old_value=None,
        new_value="27AAAAA0000A1ZZ",
        corrected_at="2026-09-02T00:00:00+00:00",
    )
    apply_correction_to_invoice(correction)
    assert len(fake_client.tables["invoices"]) == 1
    assert fake_client.tables["invoices"][0]["vendor_name"] == "OldVendor"


def test_apply_correction_maps_total_amount_to_amount_column(fake_client):
    # The invoices table has no total_amount column: the canonical
    # grand total lives in ``amount``.
    fake_client.table("invoices").extend([{
        "id": "inv-70", "amount": 1000.0, "status": "flagged",
    }])
    correction = Correction(
        invoice_id="inv-70",
        field_name="total_amount",
        old_value="1000.0",
        new_value="1180.5",
        corrected_at="2026-09-02T00:00:00+00:00",
    )
    apply_correction_to_invoice(correction)
    updated = fake_client.tables["invoices"][0]
    assert updated["amount"] == "1180.5"


def test_apply_correction_patches_tax_amount_column(fake_client):
    fake_client.table("invoices").extend([{
        "id": "inv-71", "tax_amount": 90.0, "status": "flagged",
    }])
    correction = Correction(
        invoice_id="inv-71",
        field_name="tax_amount",
        old_value="90.0",
        new_value="180.0",
        corrected_at="2026-09-02T00:00:00+00:00",
    )
    apply_correction_to_invoice(correction)
    updated = fake_client.tables["invoices"][0]
    assert updated["tax_amount"] == "180.0"


def test_apply_correction_invoice_date_stays_extraction_only(fake_client):
    # invoice_date has no invoices column: only the extraction row.
    fake_client.table("invoices").extend([{
        "id": "inv-72", "invoice_number": "INV-72",
    }])
    correction = Correction(
        invoice_id="inv-72",
        field_name="invoice_date",
        old_value=None,
        new_value="2026-03-15",
        corrected_at="2026-09-02T00:00:00+00:00",
    )
    apply_correction_to_invoice(correction)
    assert len(fake_client.tables["extraction_fields"]) == 1
    assert "invoice_date" not in fake_client.tables["invoices"][0]
