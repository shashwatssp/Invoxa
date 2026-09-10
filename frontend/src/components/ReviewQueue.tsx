import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  fetchReviewQueue,
  friendlyError,
  resolveReview,
  submitCorrection,
  type ReviewQueueItem,
} from '@/lib/api';
import { formatINR, formatDate, statusTone } from '@/lib/format';
import { ReceiptViewer } from '@/components/ReceiptViewer';

// Fields an operator is most likely to need to correct.
const EDITABLE_FIELDS = [
  'invoice_number',
  'invoice_date',
  'due_date',
  'amount',
  'tax_amount',
  'total_amount',
] as const;

type EditableField = (typeof EDITABLE_FIELDS)[number];

interface DraftCorrection {
  field_name: string;
  new_value: string;
}

export function ReviewQueue() {
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, DraftCorrection>>({});
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});
  // Receipts the approver has opened at least once this session (approve lock).
  const [viewed, setViewed] = useState<Record<string, boolean>>({});
  const [viewerInvoiceId, setViewerInvoiceId] = useState<string | null>(null);

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const queue = await fetchReviewQueue();
      setItems(queue);
    } catch (err) {
      setError(friendlyError(err, 'Could not load the review queue.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const updateDraft = (reviewId: string, fieldName: string, value: string) => {
    setDraft((current) => ({ ...current, [reviewId]: { field_name: fieldName, new_value: value } }));
  };

  const handleApprove = async (reviewId: string) => {
    setSubmitting((current) => ({ ...current, [reviewId]: true }));
    try {
      await resolveReview(reviewId, true);
      setItems((current) => current.filter((item) => item.id !== reviewId));
    } catch (err) {
      setError(friendlyError(err, 'Could not approve this item.'));
    } finally {
      setSubmitting((current) => ({ ...current, [reviewId]: false }));
    }
  };

  const handleSubmitCorrection = async (event: FormEvent<HTMLFormElement>, reviewId: string) => {
    event.preventDefault();
    const correction = draft[reviewId];
    if (!correction || !correction.new_value.trim()) return;

    setSubmitting((current) => ({ ...current, [reviewId]: true }));
    try {
      await submitCorrection(reviewId, correction.field_name, correction.new_value.trim());
      setItems((current) => current.filter((item) => item.id !== reviewId));
      setDraft((current) => {
        const next = { ...current };
        delete next[reviewId];
        return next;
      });
    } catch (err) {
      setError(friendlyError(err, 'Could not save the correction.'));
    } finally {
      setSubmitting((current) => ({ ...current, [reviewId]: false }));
    }
  };

  if (loading) {
    return (
      <section className="card">
        <h2>Review queue</h2>
        <div className="skeleton skeleton-line skeleton-line--w60" />
        <div className="skeleton skeleton-line skeleton-line--w40" />
      </section>
    );
  }

  return (
    <section className="card">
      <div className="card__header">
        <h2>Review queue</h2>
        {items.length > 0 && <span className="badge badge--medium">{items.length} pending</span>}
      </div>
      {error && <div className="error-banner">{error}</div>}
      {items.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>Nothing to review. You're all caught up.</p>
      ) : (
        <div className="field-grid">
          {items.map((item) => {
            const invoiceNumber = item.invoices?.invoice_number ?? '(no number)';
            const amount = item.invoices?.amount ?? null;
            const submittingItem = Boolean(submitting[item.id]);
            const hasViewed = Boolean(viewed[item.invoice_id]);
            const selectedField = draft[item.id]?.field_name ?? EDITABLE_FIELDS[0];
            return (
              <article key={item.id} className="card" style={{ background: 'var(--color-bg)' }}>
                <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <div>
                    <strong>{invoiceNumber}</strong>
                    <div className="muted" style={{ fontSize: '0.8rem' }}>{formatDate(item.created_at)}</div>
                  </div>
                  <span className={`badge badge--${statusTone(item.invoices?.status ?? item.status)}`}>
                    {(item.invoices?.status ?? item.status).replace('_', ' ')}
                  </span>
                </header>
                <p className="muted" style={{ margin: '0.5rem 0' }}>{item.reason}</p>
                <dl className="field-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
                  <div className="field">
                    <dt className="field__label">Amount</dt>
                    <dd className="field__value">{formatINR(amount)}</dd>
                  </div>
                  <div className="field">
                    <dt className="field__label">Original document</dt>
                    <dd className="field__value">
                      <button
                        type="button"
                        className={`button button--secondary${hasViewed ? ' viewed-check' : ''}`}
                        onClick={() => setViewerInvoiceId(item.invoice_id)}
                      >
                        {hasViewed ? 'View receipt ✓' : 'View receipt'}
                      </button>
                    </dd>
                  </div>
                </dl>
                <div className="muted" style={{ fontSize: '0.8rem' }}>
                  <Link to={`/app/invoices/${item.invoice_id}`}>Open full detail page</Link>
                </div>
                <form onSubmit={(event) => handleSubmitCorrection(event, item.id)} style={{ marginTop: '0.75rem' }}>
                  <label className="field__label" htmlFor={`field-${item.id}`}>Correct a field</label>
                  <div className="row-actions" style={{ marginTop: '0.35rem', alignItems: 'center' }}>
                    <select
                      id={`field-${item.id}`}
                      className="input"
                      style={{ flex: '0 1 auto', width: 'auto' }}
                      value={selectedField}
                      onChange={(event) => updateDraft(item.id, event.target.value, draft[item.id]?.new_value ?? '')}
                    >
                      {EDITABLE_FIELDS.map((name: EditableField) => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </select>
                    <input
                      className="input"
                      type="text"
                      placeholder="corrected value"
                      value={draft[item.id]?.new_value ?? ''}
                      onChange={(event) => updateDraft(item.id, selectedField, event.target.value)}
                      style={{ flex: 1 }}
                    />
                  </div>
                  <div className="row-actions" style={{ marginTop: '0.6rem' }}>
                    <button
                      type="submit"
                      className="button"
                      disabled={submittingItem || !hasViewed || !(draft[item.id]?.new_value ?? '').trim()}
                    >
                      {submittingItem ? 'Saving…' : 'Save correction'}
                    </button>
                    <button
                      type="button"
                      className="button button--secondary"
                      onClick={() => handleApprove(item.id)}
                      disabled={submittingItem || !hasViewed}
                      title={hasViewed ? 'Approve this receipt' : 'View the receipt first to unlock approval'}
                    >
                      Approve as-is
                    </button>
                  </div>
                  <div className="muted" style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>
                    {hasViewed
                      ? 'Approving marks the invoice as reviewed and removes it from this queue.'
                      : 'Open the receipt once to unlock approval. No blind approvals.'}
                  </div>
                </form>
              </article>
            );
            })}
        </div>
      )}

      {viewerInvoiceId && (
        <ReceiptViewer
          invoiceId={viewerInvoiceId}
          title="Receipt under review"
          onClose={() => setViewerInvoiceId(null)}
          onOpened={() => setViewed((current) => ({ ...current, [viewerInvoiceId]: true }))}
        />
      )}
    </section>
  );
}
