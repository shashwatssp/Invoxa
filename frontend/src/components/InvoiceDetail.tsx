import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  deleteInvoice,
  EXPENSE_CATEGORIES,
  fetchInvoice,
  friendlyError,
  setInvoiceCategory,
  updateInvoiceField,
  type InvoiceDetail as InvoiceDetailData,
} from '@/lib/api';
import { confidenceBand, formatDate, formatINR, statusTone } from '@/lib/format';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ReceiptViewer } from '@/components/ReceiptViewer';

const FIELD_LABELS: Record<string, string> = {
  vendor_name: 'Vendor',
  vendor_gstin: 'GSTIN',
  invoice_number: 'Invoice number',
  invoice_date: 'Invoice date',
  due_date: 'Due date',
  amount: 'Amount',
  tax_amount: 'Tax',
  total_amount: 'Total',
};

function ConfidenceMeter({ value }: { value: number | null | undefined }) {
  const band = confidenceBand(value);
  const pct = value == null ? 0 : Math.round(value * 100);
  return (
    <div style={{ minWidth: '7rem' }}>
      <div className="meter">
        <div className={`meter__fill meter__fill--${band}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="muted" style={{ fontSize: '0.72rem', marginTop: '0.2rem' }}>{pct}%</div>
    </div>
  );
}

export function InvoiceDetail() {
  const { invoiceId } = useParams<{ invoiceId: string }>();
  const navigate = useNavigate();
  const [invoice, setInvoice] = useState<InvoiceDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showReceipt, setShowReceipt] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editing, setEditing] = useState<{ field: string; value: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [category, setCategory] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!invoiceId) return;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchInvoice(invoiceId);
        if (!cancelled) {
          setInvoice(data);
          setCategory(data.category ?? null);
        }
      } catch (err) {
        if (!cancelled) setError(friendlyError(err, 'Could not load this invoice.'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [invoiceId]);

  if (loading) {
    return (
      <div className="card">
        <div className="skeleton skeleton-line skeleton-line--w40" />
        <div className="skeleton skeleton-line skeleton-line--w60" />
        <div className="skeleton skeleton-line" />
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div>
        {error && <div className="error-banner">{error}</div>}
        <Link className="button button--secondary" to="/app">Back to dashboard</Link>
      </div>
    );
  }

  const fields = invoice.extraction_fields ?? [];
  const overall = fields.length
    ? fields.reduce((sum, f) => sum + (f.confidence ?? 0), 0) / fields.length
    : null;

  const EDITABLE = ['invoice_number', 'invoice_date', 'due_date', 'amount', 'tax_amount', 'total_amount'];

  const saveEdit = async () => {
    if (!invoiceId || !editing || !editing.value.trim()) return;
    setSaving(true);
    try {
      await updateInvoiceField(invoiceId, editing.field, editing.value.trim());
      const data = await fetchInvoice(invoiceId);
      setInvoice(data);
      setEditing(null);
    } catch (err) {
      setError(friendlyError(err, 'Could not save the change.'));
    } finally {
      setSaving(false);
    }
  };

  const changeCategory = async (next: string | null) => {
    if (!invoiceId) return;
    setCategory(next);
    try {
      await setInvoiceCategory(invoiceId, next);
    } catch (err) {
      setError(friendlyError(err, 'Could not set the category.'));
    }
  };

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>{invoice.invoice_number ?? 'Invoice'}</h1>
          <p className="muted">Added {formatDate(invoice.created_at)}</p>
        </div>
        <span className={`badge badge--${statusTone(invoice.status)}`}>
          {invoice.status.replace('_', ' ')}
        </span>
      </header>

      <section className="card">
        <div className="card__header">
          <h2>Summary</h2>
          <ConfidenceMeter value={overall} />
        </div>
        <div className="detail-row" style={{ marginBottom: '0.75rem' }}>
          <span className="muted">Expense category</span>
          <select
            className="input"
            style={{ width: 'auto', minHeight: '2.4rem', fontSize: '0.88rem' }}
            value={category ?? ''}
            onChange={(e) => void changeCategory(e.target.value || null)}
            aria-label="Expense category"
          >
            <option value="">Uncategorized</option>
            {EXPENSE_CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>{cat.replace('_', ' ')}</option>
            ))}
          </select>
        </div>
        <div className="detail-grid">
          <div className="field">
            <span className="field__label">Amount</span>
            <span className="field__value">{formatINR(invoice.amount)}</span>
          </div>
          <div className="field">
            <span className="field__label">Due date</span>
            <span className="field__value">{formatDate(invoice.due_date)}</span>
          </div>
          <div className="field">
            <span className="field__label">Original document</span>
            <span className="field__value">
              <button type="button" className="button button--secondary" onClick={() => setShowReceipt(true)}>
                View receipt PDF
              </button>
            </span>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card__header">
          <h2>Extracted fields</h2>
        </div>
        {fields.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No fields were extracted from this document.
          </p>
        ) : (
          <div>
            {fields.map((f) => {
              const editable = EDITABLE.includes(f.field_name);
              const isEditing = editing?.field === f.field_name;
              return (
                <div key={`${f.field_name}-${f.created_at}`} className="detail-row">
                  <span className="muted">{FIELD_LABELS[f.field_name] ?? f.field_name}</span>
                  {isEditing ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                      <input
                        className="input"
                        style={{ width: '10rem', minHeight: '2.2rem' }}
                        value={editing.value}
                        autoFocus
                        onChange={(e) => setEditing({ field: f.field_name, value: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void saveEdit();
                          if (e.key === 'Escape') setEditing(null);
                        }}
                        aria-label={`New value for ${FIELD_LABELS[f.field_name] ?? f.field_name}`}
                      />
                      <button type="button" className="button button--small" onClick={() => void saveEdit()} disabled={saving}>
                        {saving ? 'Saving…' : 'Save'}
                      </button>
                      <button type="button" className="button button--secondary button--small" onClick={() => setEditing(null)} disabled={saving}>
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.6rem' }}>
                      <strong>{f.raw_value ?? '-'}</strong>
                      <ConfidenceMeter value={f.confidence} />
                      {editable && (
                        <button
                          type="button"
                          className="linklike"
                          onClick={() => setEditing({ field: f.field_name, value: f.raw_value ?? '' })}
                        >
                          Edit
                        </button>
                      )}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <div style={{ marginTop: '1rem', display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        <Link className="button button--secondary" to="/app">Back to dashboard</Link>
        <button
          type="button"
          className="button button--danger"
          style={{ marginLeft: 'auto' }}
          onClick={() => setConfirmDelete(true)}
        >
          Delete invoice
        </button>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this invoice?"
        body={`This permanently removes ${invoice.invoice_number ?? 'this invoice'}, its receipt file, and its review entry. This cannot be undone.`}
        confirmLabel="Delete permanently"
        danger
        busy={deleting}
        onConfirm={async () => {
          if (!invoiceId) return;
          setDeleting(true);
          try {
            await deleteInvoice(invoiceId);
            navigate('/app', { replace: true });
          } catch (err) {
            setError(friendlyError(err, 'Could not delete this invoice.'));
            setConfirmDelete(false);
          } finally {
            setDeleting(false);
          }
        }}
        onClose={() => setConfirmDelete(false)}
      />

      {showReceipt && invoiceId && (
        <ReceiptViewer
          invoiceId={invoiceId}
          title={invoice.invoice_number ?? 'Original receipt'}
          onClose={() => setShowReceipt(false)}
        />
      )}
    </div>
  );
}
