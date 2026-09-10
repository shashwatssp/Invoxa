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
import { ReceiptThumb } from '@/components/ReceiptThumb';

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

/** Pull the overall confidence the pipeline stamped into the queue reason. */
function confidenceFromReason(reason: string | null | undefined): number | null {
  if (!reason) return null;
  const match = reason.match(/overall:\s*([\d.]+)/i);
  return match ? Number(match[1]) : null;
}

function confidenceBadge(value: number | null) {
  if (value === null || Number.isNaN(value)) return null;
  const tone = value >= 0.85 ? 'high' : value >= 0.7 ? 'medium' : 'low';
  return <span className={`badge badge--${tone}`}>{Math.round(value * 100)}%</span>;
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
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const queue = await fetchReviewQueue();
      setItems(queue);
      setSelectedId((current) => current ?? queue[0]?.id ?? null);
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

  const markViewed = (invoiceId: string) => {
    setViewed((current) => ({ ...current, [invoiceId]: true }));
  };

  const removeItem = (reviewId: string, mutate: (next: ReviewQueueItem[]) => ReviewQueueItem[]) => {
    setItems((current) => {
      const next = mutate(current);
      setSelectedId((sel) => {
        if (sel !== reviewId) return sel;
        return next[0]?.id ?? null;
      });
      return next;
    });
  };

  const handleApprove = async (reviewId: string) => {
    setSubmitting((current) => ({ ...current, [reviewId]: true }));
    try {
      await resolveReview(reviewId, true);
      removeItem(reviewId, (current) => current.filter((item) => item.id !== reviewId));
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
      removeItem(reviewId, (current) => current.filter((item) => item.id !== reviewId));
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

  const selectedItem = items.find((item) => item.id === selectedId) ?? null;

  // The correction + approval form. Rendered in the detail pane on desktop
  // and inline under each card on mobile (CSS picks the visible one).
  const actionsForm = (item: ReviewQueueItem, idPrefix: string) => {
    const submittingItem = Boolean(submitting[item.id]);
    const hasViewed = Boolean(viewed[item.invoice_id]);
    const selectedField = draft[item.id]?.field_name ?? EDITABLE_FIELDS[0];
    return (
      <form onSubmit={(event) => handleSubmitCorrection(event, item.id)} style={{ marginTop: '0.75rem' }}>
        <label className="field__label" htmlFor={`field-${idPrefix}-${item.id}`}>Correct a field</label>
        <div className="row-actions" style={{ marginTop: '0.35rem', alignItems: 'center' }}>
          <select
            id={`field-${idPrefix}-${item.id}`}
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
            className="button"
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
    );
  };

  const openViewer = (item: ReviewQueueItem) => {
    setSelectedId(item.id);
    setViewerInvoiceId(item.invoice_id);
  };

  const queueCard = (item: ReviewQueueItem) => {
    const invoiceNumber = item.invoices?.invoice_number ?? '(no number)';
    const amount = item.invoices?.amount ?? null;
    const hasViewed = Boolean(viewed[item.invoice_id]);
    const confidence = confidenceFromReason(item.reason);
    return (
      <article
        key={item.id}
        className={`review-item card${item.id === selectedId ? ' review-item--active' : ''}`}
        onClick={() => setSelectedId(item.id)}
      >
        <button
          type="button"
          className="review-item__thumb"
          onClick={(event) => {
            event.stopPropagation();
            openViewer(item);
          }}
          title="View the full receipt"
        >
          <ReceiptThumb invoiceId={item.invoice_id} />
        </button>
        <div className="review-item__body">
          <header className="review-item__head">
            <div className="review-item__title">
              <strong>{invoiceNumber}</strong>
              <span className="muted" style={{ fontSize: '0.8rem' }}>{formatDate(item.created_at)}</span>
            </div>
            <span className={`badge badge--${statusTone(item.invoices?.status ?? item.status)}`}>
              {(item.invoices?.status ?? item.status).replace('_', ' ')}
            </span>
          </header>
          <div className="review-item__meta">
            <span className="review-item__amount">{formatINR(amount)}</span>
            {confidenceBadge(confidence)}
            {hasViewed && <span className="badge badge--high">viewed ✓</span>}
          </div>
          <p className="muted review-item__reason">{item.reason}</p>
          <div className="review-item__links muted" style={{ fontSize: '0.8rem' }}>
            <button
              type="button"
              className="linklike"
              onClick={(event) => {
                event.stopPropagation();
                openViewer(item);
              }}
            >
              {hasViewed ? 'View receipt ✓' : 'View receipt'}
            </button>
            <Link to={`/app/invoices/${item.invoice_id}`} onClick={(event) => event.stopPropagation()}>
              Full detail
            </Link>
          </div>
          <div className="review-item__actions">{actionsForm(item, 'card')}</div>
        </div>
      </article>
    );
  };

  return (
    <section>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="card__header">
          <h2>Review queue</h2>
          {items.length > 0 && <span className="badge badge--medium">{items.length} pending</span>}
        </div>
        {error && <div className="error-banner">{error}</div>}
        {items.length === 0 && (
          <p className="muted" style={{ margin: 0 }}>Nothing to review. You're all caught up.</p>
        )}
      </div>

      {items.length > 0 && (
        <div className="review-workspace">
          <div className="review-list">
            {items.map((item) => queueCard(item))}
          </div>

          <aside className="review-detail card">
            {selectedItem ? (
              <>
                <div className="card__header">
                  <h2>
                    {selectedItem.invoices?.invoice_number ?? '(no number)'}
                  </h2>
                  <span className={`badge badge--${statusTone(selectedItem.invoices?.status ?? selectedItem.status)}`}>
                    {(selectedItem.invoices?.status ?? selectedItem.status).replace('_', ' ')}
                  </span>
                </div>
                <p className="muted" style={{ marginTop: 0 }}>{selectedItem.reason}</p>
                <button
                  type="button"
                  className="review-detail__preview"
                  onClick={() => setViewerInvoiceId(selectedItem.invoice_id)}
                  title="Open the full receipt"
                >
                  <ReceiptThumb invoiceId={selectedItem.invoice_id} large />
                  <span className="review-detail__hint">Open full PDF</span>
                </button>
                {actionsForm(selectedItem, 'pane')}
              </>
            ) : (
              <p className="muted">Select an invoice from the queue.</p>
            )}
          </aside>
        </div>
      )}

      {viewerInvoiceId && (() => {
        const reviewItem = items.find((item) => item.invoice_id === viewerInvoiceId);
        return (
          <ReceiptViewer
            invoiceId={viewerInvoiceId}
            title="Receipt under review"
            onClose={() => setViewerInvoiceId(null)}
            onOpened={() => markViewed(viewerInvoiceId)}
            footerAction={
              reviewItem
                ? {
                    label: submitting[reviewItem.id] ? 'Approving…' : 'Approve as-is',
                    disabled: !viewed[viewerInvoiceId] || Boolean(submitting[reviewItem.id]),
                    onClick: () => {
                      void handleApprove(reviewItem.id);
                      setViewerInvoiceId(null);
                    },
                  }
                : undefined
            }
          />
        );
      })()}
    </section>
  );
}
