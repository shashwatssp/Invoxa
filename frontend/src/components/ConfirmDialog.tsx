import { useEffect } from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/** Centered modal (bottom sheet on mobile) for destructive confirmations. */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="viewer-backdrop export-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="export-panel"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="export-panel__handle" aria-hidden />
        <div className="export-panel__header">
          <h2>{title}</h2>
          <button type="button" className="linklike" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="export-panel__body">
          <p style={{ margin: '0 0 1rem' }}>{body}</p>
          <div className="row-actions">
            <button
              type="button"
              className={`button${danger ? ' button--danger' : ''}`}
              onClick={onConfirm}
              disabled={busy}
            >
              {busy ? 'Working…' : confirmLabel}
            </button>
            <button
              type="button"
              className="button button--secondary"
              onClick={onClose}
              disabled={busy}
            >
              {cancelLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
