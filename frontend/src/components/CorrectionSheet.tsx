import { useEffect, useRef, useState } from 'react';
import {
  fetchInvoice,
  friendlyError,
  submitCorrections,
  type CorrectionInput,
  type ReviewQueueItem,
} from '@/lib/api';
import { statusTone } from '@/lib/format';

type FieldKind = 'text' | 'amount' | 'date';

interface FieldConfig {
  name: string;
  label: string;
  kind: FieldKind;
}

// Same field set the backend whitelist (EDITABLE_FIELDS) allows.
const FIELDS: FieldConfig[] = [
  { name: 'invoice_number', label: 'Invoice number', kind: 'text' },
  { name: 'invoice_date', label: 'Invoice date', kind: 'date' },
  { name: 'due_date', label: 'Due date', kind: 'date' },
  { name: 'amount', label: 'Amount', kind: 'amount' },
  { name: 'tax_amount', label: 'Tax amount', kind: 'amount' },
  { name: 'total_amount', label: 'Total amount', kind: 'amount' },
];

interface FieldState {
  value: string;
  /** Extracted value as stored (shown as a hint when it differs). */
  raw: string | null;
  confidence: number | null;
}

/** DD/MM/YYYY, DD-MM-YYYY or ISO -> ISO for <input type="date">, else ''. */
function toIsoDate(value: string | null | undefined): string {
  if (!value) return '';
  const v = value.trim();
  const dmy = v.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  if (dmy) {
    const [, d, m, y] = dmy;
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
  }
  return /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : '';
}

/** Same normalization the server applies, for instant inline feedback. */
function validateValue(config: FieldConfig, value: string): string | null {
  const v = value.trim();
  if (!v) return 'Enter a value or leave the field unchanged.';
  if (config.kind === 'amount') {
    const cleaned = v.replace(/[₹\s,]/g, '');
    if (cleaned === '' || !Number.isFinite(Number(cleaned))) {
      return 'Enter a valid amount, e.g. 1180.50';
    }
  }
  if (config.kind === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(v)) {
    return 'Enter a valid date.';
  }
  return null;
}

function confidenceBadge(value: number | null) {
  if (value === null || Number.isNaN(value)) return null;
  const tone = value >= 0.85 ? 'high' : value >= 0.7 ? 'medium' : 'low';
  return <span className={`badge badge--${tone}`}>{Math.round(value * 100)}%</span>;
}

interface CorrectionSheetProps {
  item: ReviewQueueItem;
  onClose: () => void;
  /** Fired after a successful save (the item left the queue). */
  onSaved: (message: string) => void;
}

/**
 * Full field-wise correction sheet: every editable field at once,
 * prefilled with the extracted values, validated inline, and saved in a
 * single batch call. Centered panel on desktop, bottom sheet on mobile.
 */
export function CorrectionSheet({ item, onClose, onSaved }: CorrectionSheetProps) {
  const invoiceNumber = item.invoices?.invoice_number ?? '(no number)';
  const invoiceStatus = item.invoices?.status ?? item.status;

  const [loading, setLoading] = useState(true);
  const [fields, setFields] = useState<Record<string, FieldState>>({});
  const [initialValues, setInitialValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const firstFieldRef = useRef<HTMLInputElement | null>(null);

  const hasChanges = FIELDS.some(
    ({ name }) => (fields[name]?.value ?? '').trim() !== (initialValues[name] ?? ''),
  );

  // Load the invoice detail once for prefill (extraction values first,
  // canonical invoice columns as fallback).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const detail = await fetchInvoice(item.invoice_id);
        if (cancelled) return;

        const extracted = new Map(
          (detail.extraction_fields ?? []).map((f) => [f.field_name, f]),
        );
        const next: Record<string, FieldState> = {};
        const initial: Record<string, string> = {};
        for (const { name, kind } of FIELDS) {
          const row = extracted.get(name);
          const fallback =
            name === 'invoice_number'
              ? detail.invoice_number
              : name === 'amount'
                ? detail.amount != null ? String(detail.amount) : null
                : name === 'due_date'
                  ? detail.due_date
                  : null;
          const raw = row?.raw_value ?? (fallback ?? null);
          // Dates need ISO for the native picker; everything else shows
          // the extracted value as-is.
          const value = kind === 'date' ? toIsoDate(raw) : raw ?? '';
          next[name] = { value, raw, confidence: row?.confidence ?? null };
          initial[name] = value;
        }
        setFields(next);
        setInitialValues(initial);
      } catch (err) {
        if (!cancelled) setFormError(friendlyError(err, 'Could not load the invoice details.'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [item.invoice_id]);

  // Escape closes; the background page does not scroll behind the sheet.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  // Focus lands on the first field once the form is ready.
  useEffect(() => {
    if (!loading) firstFieldRef.current?.focus();
  }, [loading]);

  const setValue = (name: string, value: string) => {
    setFields((current) => ({ ...current, [name]: { ...current[name], value } }));
    setErrors((current) => {
      if (!current[name]) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
  };

  const handleSave = async () => {
    // Validate every touched field first; abort on the first problem.
    const changed: CorrectionInput[] = [];
    const nextErrors: Record<string, string> = {};
    for (const config of FIELDS) {
      const value = (fields[config.name]?.value ?? '').trim();
      if (value === initialValues[config.name]) continue;
      const error = validateValue(config, value);
      if (error) {
        nextErrors[config.name] = error;
      } else {
        changed.push({ field_name: config.name, new_value: value });
      }
    }
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    if (changed.length === 0) return;

    setSubmitting(true);
    setFormError(null);
    try {
      await submitCorrections(item.id, changed);
      onSaved('Correction saved — the invoice is marked reviewed.');
    } catch (err) {
      // A 422 detail looks like "amount: 'x' is not a valid amount …";
      // pin it to the field so the reviewer sees exactly what to fix.
      const detail =
        typeof err === 'object' && err !== null && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined;
      if (typeof detail === 'string') {
        const fieldName = detail.split(':')[0]?.trim();
        if (fieldName && FIELDS.some((f) => f.name === fieldName)) {
          setErrors({ [fieldName]: detail.slice(detail.indexOf(':') + 1).trim() });
        } else {
          setFormError(detail);
        }
      } else {
        setFormError(friendlyError(err, 'Could not save the corrections.'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="viewer-backdrop export-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget && !submitting) onClose();
      }}
    >
      <div className="export-panel correction-sheet" role="dialog" aria-modal="true" aria-label="Correct details">
        <div className="export-panel__handle" aria-hidden />
        <header className="export-panel__header">
          <div>
            <h2>Correct details</h2>
            <p className="correction-sheet__invoice muted">
              {invoiceNumber}
              <span className={`badge badge--${statusTone(invoiceStatus)}`}>
                {invoiceStatus.replace('_', ' ')}
              </span>
            </p>
          </div>
          <button type="button" className="linklike" onClick={onClose} disabled={submitting}>
            Close
          </button>
        </header>
        <div className="export-panel__body">
          {item.reason && <p className="muted correction-sheet__reason">{item.reason}</p>}
          {formError && <div className="error-banner" style={{ margin: 0 }}>{formError}</div>}

          {loading ? (
            <div className="correction-sheet__loading">
              <div className="spinner" />
              <p className="muted">Loading extracted values…</p>
            </div>
          ) : (
            <div className="correction-grid">
              {FIELDS.map((config, index) => {
                const state = fields[config.name] ?? { value: '', raw: null, confidence: null };
                const error = errors[config.name];
                const hint = state.raw !== null && state.raw.trim() !== '' && state.raw.trim() !== state.value.trim()
                  ? `Extracted: ${state.raw}`
                  : null;
                return (
                  <label className="correction-field" key={config.name} htmlFor={`corr-${config.name}`}>
                    <span className="correction-field__label">
                      {config.label}
                      {confidenceBadge(state.confidence)}
                    </span>
                    <input
                      id={`corr-${config.name}`}
                      ref={index === 0 ? firstFieldRef : undefined}
                      className="input"
                      type={config.kind === 'date' ? 'date' : 'text'}
                      inputMode={config.kind === 'amount' ? 'decimal' : undefined}
                      autoComplete="off"
                      value={state.value}
                      aria-invalid={error ? true : undefined}
                      onChange={(event) => setValue(config.name, event.target.value)}
                    />
                    {hint && !error && <span className="correction-field__hint muted">{hint}</span>}
                    {error && <span className="correction-field__error">{error}</span>}
                  </label>
                );
              })}
            </div>
          )}
        </div>
        <footer className="export-panel__footer correction-sheet__footer">
          {!loading && !hasChanges && (
            <span className="muted correction-sheet__footer-hint">
              Edit a field to enable saving.
            </span>
          )}
          <button
            type="button"
            className="button"
            onClick={() => void handleSave()}
            disabled={loading || submitting || !hasChanges}
          >
            {submitting ? 'Saving…' : 'Save corrections'}
          </button>
        </footer>
      </div>
    </div>
  );
}
