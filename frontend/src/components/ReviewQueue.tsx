import { useEffect, useState, type FormEvent } from 'react';
import {
  fetchReviewQueue,
  resolveReview,
  submitCorrection,
  type ReviewQueueItem,
} from '@/lib/api';
import { formatINR, formatDate } from '@/lib/format';

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

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const queue = await fetchReviewQueue();
      setItems(queue);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load review queue');
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
      setError(err instanceof Error ? err.message : 'Approve failed');
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
      setError(err instanceof Error ? err.message : 'Correction failed');
    } finally {
      setSubmitting((current) => ({ ...current, [reviewId]: false }));
    }
  };

  if (loading) {
    return (
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Review queue</h2>
        <div className="spinner-page"><div className="spinner" /></div>
      </section>
    );
  }

  return (
    <section className="card">
      <h2 style={{ marginTop: 0 }}>Review queue</h2>
      {error && <div className="error-banner">{error}</div>}
      {items.length === 0 ? (
        <p className="muted">Nothing to review. Sweet.</p>
      ) : (
        <div className="field-grid">
          {items.map((item) => {
            const invoiceNumber = item.invoices?.invoice_number ?? '(no number)';
            const amount = item.invoices?.amount ?? null;
            const submittingItem = Boolean(submitting[item.id]);
            const selectedField = draft[item.id]?.field_name ?? EDITABLE_FIELDS[0];
            return (
              <article key={item.id} className="card" style={{ background: 'var(--color-bg)' }}>
                <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <div>
                    <strong>{invoiceNumber}</strong>
                    <div className="muted" style={{ fontSize: '0.8rem' }}>{formatDate(item.created_at)}</div>
                  </div>
                  <span className="badge badge--low">{item.invoices?.status ?? item.status}</span>
                </header>
                <p className="muted" style={{ margin: '0.5rem 0' }}>{item.reason}</p>
                <dl className="field-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
                  <div className="field">
                    <dt className="field__label">Amount</dt>
                    <dd className="field__value">{formatINR(amount)}</dd>
                  </div>
                </dl>
                <form onSubmit={(event) => handleSubmitCorrection(event, item.id)} style={{ marginTop: '0.75rem' }}>
                  <label className="field__label" htmlFor={`field-${item.id}`}>Correct a field</label>
                  <div className="row-actions" style={{ marginTop: '0.35rem', alignItems: 'center' }}>
                    <select
                      id={`field-${item.id}`}
                      value={selectedField}
                      onChange={(event) => updateDraft(item.id, event.target.value, draft[item.id]?.new_value ?? '')}
                    >
                      {EDITABLE_FIELDS.map((name: EditableField) => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </select>
                    <input
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
                      disabled={submittingItem || !(draft[item.id]?.new_value ?? '').trim()}
                    >
                      {submittingItem ? 'Saving…' : 'Save correction'}
                    </button>
                    <button
                      type="button"
                      className="button button--secondary"
                      onClick={() => handleApprove(item.id)}
                      disabled={submittingItem}
                    >
                      Approve as-is
                    </button>
                  </div>
                </form>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
