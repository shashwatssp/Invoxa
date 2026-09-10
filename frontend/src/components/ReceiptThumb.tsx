import { useEffect, useState } from 'react';
import { fetchInvoicePreview } from '@/lib/api';

interface ReceiptThumbProps {
  invoiceId: string;
  /** Render a larger preview (detail pane) instead of the small thumb. */
  large?: boolean;
}

/**
 * Renders page 1 of the stored receipt as an image (authenticated blob).
 * Falls back to a neutral PDF tile when the preview cannot be rendered
 * (e.g. scanned or corrupt documents).
 */
export function ReceiptThumb({ invoiceId, large = false }: ReceiptThumbProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    setUrl(null);
    setFailed(false);
    fetchInvoicePreview(invoiceId)
      .then((blob) => {
        if (cancelled) {
          URL.revokeObjectURL(URL.createObjectURL(blob));
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [invoiceId]);

  const cls = large ? 'thumb thumb--large' : 'thumb';

  if (failed) {
    return (
      <div className={`${cls} thumb--empty`} aria-label="Receipt preview unavailable">
        <span>PDF</span>
      </div>
    );
  }

  if (!url) {
    return (
      <div className={`${cls} thumb--loading`} aria-label="Loading receipt preview">
        <div className="spinner" />
      </div>
    );
  }

  return <img className={cls} src={url} alt="Receipt preview" loading="lazy" />;
}
