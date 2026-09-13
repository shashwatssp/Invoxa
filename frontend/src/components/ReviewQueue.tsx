import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  deleteInvoice,
  fetchReviewQueue,
  friendlyError,
  resolveReview,
  type ReviewQueueItem,
} from '@/lib/api';
import { formatINR, formatDate, statusTone } from '@/lib/format';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CorrectionSheet } from '@/components/CorrectionSheet';
import { ReceiptViewer } from '@/components/ReceiptViewer';
import { ReceiptThumb } from '@/components/ReceiptThumb';

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
  const [toast, setToast] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});
  // Review item currently open in the correction sheet (null = closed).
  const [correctionItem, setCorrectionItem] = useState<ReviewQueueItem | null>(null);
  // Receipts the approver has opened at least once this session (approve lock).
  const [viewed, setViewed] = useState<Record<string, boolean>>({});
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
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

  // Transient confirmation so the approver sees the action landed.
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const handleApprove = async (reviewId: string) => {
    setSubmitting((current) => ({ ...current, [reviewId]: true }));
    try {
      await resolveReview(reviewId, true);
      removeItem(reviewId, (current) => current.filter((item) => item.id !== reviewId));
      setToast('Approved — the invoice is marked reviewed and left the queue.');
    } catch (err) {
      setError(friendlyError(err, 'Could not approve this item.'));
    } finally {
      setSubmitting((current) => ({ ...current, [reviewId]: false }));
    }
  };

  const handleDelete = async (item: ReviewQueueItem) => {
    setDeleting(true);
    try {
      await deleteInvoice(item.invoice_id);
      removeItem(item.id, (current) => current.filter((i) => i.id !== item.id));
      setToast('Deleted — the invoice was removed from your account.');
    } catch (err) {
      setError(friendlyError(err, 'Could not delete this invoice.'));
    } finally {
      setDeleting(false);
      setConfirmDeleteId(null);
    }
  };

  const handleCorrectionSaved = (reviewId: string, message: string) => {
    setCorrectionItem(null);
    removeItem(reviewId, (current) => current.filter((item) => item.id !== reviewId));
    setToast(message);
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

  // The correction + approval actions. Rendered in the detail pane on
  // desktop and inline under each card on mobile (CSS picks the visible
  // one). Corrections open the full field-wise sheet.
  const actionsForm = (item: ReviewQueueItem) => {
    const submittingItem = Boolean(submitting[item.id]);
    return (
      <div className="row-actions review-item__form" style={{ marginTop: '0.75rem' }}>
        <button
          type="button"
          className="button"
          onClick={(event) => {
            event.stopPropagation();
            setCorrectionItem(item);
          }}
          title="Correct any field - opens a form with all fields at once"
        >
          Correct details
        </button>
        <button
          type="button"
          className="button"
          onClick={(event) => {
            event.stopPropagation();
            handleApprove(item.id);
          }}
          disabled={submittingItem}
          title="Approve this receipt"
        >
          Approve as-is
        </button>
        <button
          type="button"
          className="button button--danger"
          onClick={(event) => {
            event.stopPropagation();
            setConfirmDeleteId(item.id);
          }}
          disabled={submittingItem}
          title="Delete this invoice - use for anything uploaded by mistake"
        >
          Delete
        </button>
        <div className="muted" style={{ fontSize: '0.8rem', width: '100%' }}>
          Correcting saves every edited field at once and marks the invoice as reviewed.
        </div>
      </div>
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
          <div className="review-item__actions">{actionsForm(item)}</div>
        </div>
      </article>
    );
  };

  const pendingDelete = items.find((item) => item.id === confirmDeleteId) ?? null;

  return (
    <section>
      {toast && (
        <div className="toast toast--success" role="status">
          {toast}
        </div>
      )}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete this invoice?"
        body={`This permanently removes ${pendingDelete?.invoices?.invoice_number ?? 'the invoice'}, its receipt file, and this review entry. Use it for anything uploaded by mistake - this cannot be undone.`}
        confirmLabel="Delete permanently"
        danger
        busy={deleting}
        onConfirm={() => {
          if (pendingDelete) void handleDelete(pendingDelete);
        }}
        onClose={() => setConfirmDeleteId(null)}
      />
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
                {actionsForm(selectedItem)}
              </>
            ) : (
              <p className="muted">Select an invoice from the queue.</p>
            )}
          </aside>
        </div>
      )}

      {correctionItem && (
        <CorrectionSheet
          item={correctionItem}
          onClose={() => setCorrectionItem(null)}
          onSaved={(message) => handleCorrectionSaved(correctionItem.id, message)}
        />
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
                    disabled: Boolean(submitting[reviewItem.id]),
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
