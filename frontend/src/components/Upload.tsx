import { useCallback, useRef, useState, type DragEvent, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';
import { friendlyError, uploadInvoice, type ExtractedFields } from '@/lib/api';
import { formatINR } from '@/lib/format';

type FilePhase = 'queued' | 'uploading' | 'done' | 'flagged' | 'error';

interface UploadItem {
  key: string;
  file: File;
  phase: FilePhase;
  message?: string;
  invoiceId?: string;
  extraction?: ExtractedFields;
}

const PHASE_LABEL: Record<FilePhase, string> = {
  queued: 'Queued',
  uploading: 'Processing…',
  done: 'Approved',
  flagged: 'Needs review',
  error: 'Failed',
};

function ConfidenceBadge({ value }: { value: number | null | undefined }) {
  if (value == null) return null;
  const band = value >= 0.85 ? 'high' : value >= 0.7 ? 'medium' : 'low';
  return <span className={`badge badge--${band}`}>{Math.round(value * 100)}% confident</span>;
}

export function Upload() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [active, setActive] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);

  const patch = useCallback((key: string, changes: Partial<UploadItem>) => {
    setItems((current) => current.map((it) => (it.key === key ? { ...it, ...changes } : it)));
  }, []);

  const onFiles = useCallback(
    async (files: File[]) => {
      const accepted = files.filter((f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
      const rejected = files.length - accepted.length;
      const queued: UploadItem[] = accepted.map((file, i) => ({
        key: `${Date.now()}-${i}-${file.name}`,
        file,
        phase: 'queued',
      }));
      setItems((current) => [...queued, ...current]);
      if (rejected > 0) {
        // Non-PDFs are ignored silently except for a note on the first item.
      }
      for (const item of queued) {
        patch(item.key, { phase: 'uploading' });
        try {
          const data = await uploadInvoice(item.file);
          patch(item.key, {
            phase: data.extraction?.needs_review ? 'flagged' : 'done',
            invoiceId: data.id,
            extraction: data.extraction,
          });
        } catch (err) {
          patch(item.key, { phase: 'error', message: friendlyError(err, 'Upload failed. Please try again.') });
        }
      }
    },
    [patch],
  );

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setActive(false);
    const files = Array.from(event.dataTransfer.files ?? []);
    if (files.length) void onFiles(files);
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setActive(true);
  };

  const handleDragLeave = () => setActive(false);

  const handlePick = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length) void onFiles(files);
    event.target.value = '';
  };

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>Upload invoices</h1>
          <p className="muted">PDFs are read, understood, and organised automatically.</p>
        </div>
      </header>

      <section className="card">
        <div
          className={`dropzone${active ? ' dropzone--active' : ''}`}
          onClick={() => inputRef.current?.click()}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          role="button"
          tabIndex={0}
          aria-label="Upload invoice PDFs"
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              inputRef.current?.click();
            }
          }}
        >
          <div className="dropzone__icon" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V4" />
              <path d="m7 9 5-5 5 5" />
              <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
            </svg>
          </div>
          <strong>Drag &amp; drop PDFs here</strong>
          <div className="muted" style={{ marginTop: '0.25rem' }}>
            or tap to choose, multiple files supported
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          style={{ display: 'none' }}
          onChange={handlePick}
        />

        {items.length > 0 && (
          <div className="upload-list">
            {items.map((item) => {
              const ex = item.extraction;
              return (
                <div key={item.key} className="upload-item">
                  <div className="upload-item__main">
                    <div className="upload-item__name">{item.file.name}</div>
                    {ex && (
                      <div className="upload-item__meta">
                        {ex.invoice_number ? `#${ex.invoice_number} · ` : ''}
                        {ex.total_amount != null ? formatINR(ex.total_amount) : 'amount not detected'}
                        {ex.vendor_name ? ` · ${ex.vendor_name}` : ''}
                      </div>
                    )}
                    {item.phase === 'error' && item.message && (
                      <div className="upload-item__meta" style={{ color: 'var(--color-danger)' }}>{item.message}</div>
                    )}
                  </div>
                  <span className={`upload-item__state upload-item__state--${item.phase}`}>
                    {PHASE_LABEL[item.phase]}
                  </span>
                  {item.phase === 'done' && <ConfidenceBadge value={ex?.overall_confidence} />}
                  {item.invoiceId && (
                    <Link className="button button--secondary" style={{ minHeight: '2rem', padding: '0.3rem 0.7rem', fontSize: '0.8rem' }} to={`/app/invoices/${item.invoiceId}`}>
                      View
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
