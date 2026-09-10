import { useEffect, useRef, useState } from 'react';
import { fetchInvoiceFile, friendlyError } from '@/lib/api';

interface ReceiptViewerProps {
  invoiceId: string;
  title?: string;
  onClose: () => void;
  onOpened?: () => void; // fired once the PDF has loaded successfully
}

/**
 * Full-screen modal that streams the original receipt PDF as an
 * authenticated blob and shows it inline. On mobile browsers where
 * inline PDFs are unreliable, offers an "Open in new tab" fallback.
 */
export function ReceiptViewer({ invoiceId, title, onClose, onOpened }: ReceiptViewerProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const notified = useRef(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    fetchInvoiceFile(invoiceId)
      .then((blob) => {
        if (cancelled) {
          URL.revokeObjectURL(URL.createObjectURL(blob));
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        if (!notified.current) {
          notified.current = true;
          onOpened?.();
        }
      })
      .catch((err) => {
        if (!cancelled) setError(friendlyError(err, 'Could not load the receipt document.'));
      });

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';

    return () => {
      cancelled = true;
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceId]);

  return (
    <div className="viewer-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="Receipt document">
      <div className="viewer-panel" onClick={(event) => event.stopPropagation()}>
        <header className="viewer-panel__header">
          <strong>{title || 'Original receipt'}</strong>
          <div className="row-actions">
            {url && (
              <a className="button button--secondary" href={url} target="_blank" rel="noreferrer">
                Open in tab
              </a>
            )}
            <button type="button" className="button button--secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </header>
        {error && <div className="error-banner" style={{ margin: '1rem' }}>{error}</div>}
        {url ? (
          <iframe className="viewer-frame" src={url} title="Receipt PDF" />
        ) : (
          !error && (
            <div className="viewer-loading">
              <div className="spinner" />
              <p className="muted">Loading receipt…</p>
            </div>
          )
        )}
      </div>
    </div>
  );
}
