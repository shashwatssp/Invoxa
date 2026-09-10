import { useEffect, useRef, useState } from 'react';
import { fetchInvoiceFile, friendlyError } from '@/lib/api';

type PdfLib = typeof import('pdfjs-dist');

// pdf.js is loaded lazily (own chunk) the first time the viewer opens,
// keeping the app's initial bundle small.
let pdfLibPromise: Promise<PdfLib> | null = null;
function loadPdfLib(): Promise<PdfLib> {
  if (!pdfLibPromise) {
    pdfLibPromise = Promise.all([
      import('pdfjs-dist'),
      import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
    ]).then(([lib, worker]) => {
      lib.GlobalWorkerOptions.workerSrc = worker.default;
      return lib;
    });
  }
  return pdfLibPromise;
}

interface ReceiptViewerProps {
  invoiceId: string;
  title?: string;
  onClose: () => void;
  onOpened?: () => void; // fired once the PDF has rendered successfully
  /** Sticky bottom action (e.g. Approve) shown while the receipt is open. */
  footerAction?: { label: string; onClick: () => void; disabled?: boolean };
}

const MAX_PAGES = 10;

/**
 * Full-screen modal that streams the original receipt PDF as an
 * authenticated blob and renders it with pdf.js onto canvases.
 * Canvas rendering works on every browser, including mobile ones
 * where inline PDF iframes are not supported.
 */
export function ReceiptViewer({ invoiceId, title, onClose, onOpened, footerAction }: ReceiptViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const notified = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;

    fetchInvoiceFile(invoiceId)
      .then(async (blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setBlobUrl(objectUrl);

        const pdfjsLib = await loadPdfLib();
        const data = await blob.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data }).promise;
        const container = containerRef.current;
        if (cancelled || !container) return;

        const targetWidth = Math.min(
          container.clientWidth || 360,
          900,
        ) * (window.devicePixelRatio || 1);

        for (let pageNum = 1; pageNum <= Math.min(pdf.numPages, MAX_PAGES); pageNum++) {
          if (cancelled) return;
          const page = await pdf.getPage(pageNum);
          const base = page.getViewport({ scale: 1 });
          const scale = targetWidth / base.width;
          const viewport = page.getViewport({ scale });

          const canvas = document.createElement('canvas');
          canvas.width = Math.floor(viewport.width);
          canvas.height = Math.floor(viewport.height);
          canvas.className = 'viewer-page';
          await page.render({
            canvas,
            canvasContext: canvas.getContext('2d')!,
            viewport,
          }).promise;
          if (cancelled) return;
          container.querySelector('.viewer-loading')?.remove();
          container.appendChild(canvas);
          if (!notified.current) {
            notified.current = true;
            onOpened?.();
          }
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
            {blobUrl && (
              <a className="button button--secondary" href={blobUrl} target="_blank" rel="noreferrer">
                Open in tab
              </a>
            )}
            <button type="button" className="button button--secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </header>
        {error && <div className="error-banner" style={{ margin: '1rem' }}>{error}</div>}
        {!error && (
          <div className="viewer-pages" ref={containerRef}>
            <div className="viewer-loading">
              <div className="spinner" />
              <p className="muted">Loading receipt…</p>
            </div>
          </div>
        )}
        {footerAction && (
          <footer className="viewer-footer">
            <button
              type="button"
              className="button"
              onClick={footerAction.onClick}
              disabled={footerAction.disabled}
            >
              {footerAction.label}
            </button>
          </footer>
        )}
      </div>
    </div>
  );
}
