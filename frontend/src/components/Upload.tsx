import { useCallback, useEffect, useRef, useState, type DragEvent, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  createFolder,
  fetchFolders,
  friendlyError,
  setInvoiceFolder,
  uploadInvoice,
  type ExtractedFields,
  type FolderInfo,
} from '@/lib/api';
import { formatINR } from '@/lib/format';

/** Cache the service worker stores files shared from the OS share sheet in. */
const SHARED_FILE_CACHE = 'invoxa-shared-file-v1';
const SHARED_FILE_KEY = 'shared-file';

type FilePhase = 'queued' | 'uploading' | 'done' | 'flagged' | 'error';

interface UploadItem {
  key: string;
  file: File;
  phase: FilePhase;
  message?: string;
  invoiceId?: string;
  extraction?: ExtractedFields;
  // Folder this invoice currently sits in (may have been changed after upload).
  folderId?: string | null;
  filing?: boolean; // folder move in progress
}

const PHASE_LABEL: Record<FilePhase, string> = {
  queued: 'Queued',
  uploading: 'Processing…',
  done: 'Done',
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
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState('');
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [folderError, setFolderError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [foldersLoading, setFoldersLoading] = useState(true);

  // Transient confirmation so the user sees folder filing landed.
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const loadFolders = useCallback(async () => {
    setFoldersLoading(true);
    try {
      setFolders(await fetchFolders());
    } catch {
      // Folder list is optional sugar; uploads work without it.
    } finally {
      setFoldersLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFolders();
  }, [loadFolders]);


  const patch = useCallback((key: string, changes: Partial<UploadItem>) => {
    setItems((current) => current.map((it) => (it.key === key ? { ...it, ...changes } : it)));
  }, []);

  const onFiles = useCallback(
    async (files: File[]) => {
      const isPdf = (f: File) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf');
      const isPhoto = (f: File) => f.type.startsWith('image/') || /\.(jpe?g|png)$/i.test(f.name.toLowerCase());
      const accepted = files.filter((f) => isPdf(f) || isPhoto(f));
      const rejected = files.length - accepted.length;
      const queued: UploadItem[] = accepted.map((file, i) => ({
        key: `${Date.now()}-${i}-${file.name}`,
        file,
        phase: 'queued',
      }));
      setItems((current) => [...queued, ...current]);
      if (rejected > 0) {
        // Unsupported types are ignored silently except for a note on the first item.
      }
      for (const item of queued) {
        patch(item.key, { phase: 'uploading' });
        try {
          const data = await uploadInvoice(item.file, folderId);
          patch(item.key, {
            phase: data.extraction?.needs_review ? 'flagged' : 'done',
            invoiceId: data.id,
            extraction: data.extraction,
            folderId,
          });
        } catch (err) {
          patch(item.key, { phase: 'error', message: friendlyError(err, 'Upload failed. Please try again.') });
        }
      }
    },
    [patch, folderId],
  );

  // A file shared from the OS share sheet (WhatsApp, Photos, Files...) is
  // dropped into the cache by the service worker; pick it up once on mount.
  const onFilesRef = useRef(onFiles);
  useEffect(() => {
    onFilesRef.current = onFiles;
  }, [onFiles]);
  useEffect(() => {
    const readSharedFile = async () => {
      if (!('caches' in window)) return;
      try {
        const cache = await caches.open(SHARED_FILE_CACHE);
        const stored = await cache.match(SHARED_FILE_KEY);
        if (!stored) return;
        await cache.delete(SHARED_FILE_KEY);
        const blob = await stored.blob();
        const name = stored.headers.get('x-invoxa-filename') || 'shared-invoice.pdf';
        const type = blob.type || 'application/octet-stream';
        onFilesRef.current([new File([blob], name, { type })]);
      } catch {
        // Shared-file pickup is best-effort; manual upload always works.
      }
    };
    void readSharedFile();
  }, []);

  /**
   * Destination changed: every completed upload from this session is
   * (re)filed into the chosen folder, with a visible Done confirmation.
   */
  const onFolderChange = useCallback(
    async (nextId: string | null, nameHint?: string) => {
      setFolderId(nextId);
      setFolderError(null);
      const filed = items.filter(
        (it) => it.invoiceId && (it.phase === 'done' || it.phase === 'flagged'),
      );
      const toMove = filed.filter((it) => (it.folderId ?? null) !== nextId);
      if (toMove.length === 0) return;

      toMove.forEach((it) => patch(it.key, { filing: true }));
      let moved = 0;
      for (const it of toMove) {
        try {
          await setInvoiceFolder(it.invoiceId!, nextId);
          patch(it.key, { folderId: nextId, filing: false });
          moved += 1;
        } catch (err) {
          patch(it.key, { filing: false });
          setFolderError(friendlyError(err, 'Could not move the invoice to the folder.'));
        }
      }
      if (moved > 0) {
        const name = nextId
          ? nameHint ?? folders.find((f) => f.id === nextId)?.name ?? 'the folder'
          : 'No folder';
        setToast(
          moved === 1
            ? `Done — 1 invoice added to ${name}.`
            : `Done — ${moved} invoices added to ${name}.`,
        );
      }
    },
    [items, folders, patch],
  );

  const onCreateFolder = useCallback(async () => {
    const name = newFolderName.trim();
    if (!name) return;
    setFolderError(null);
    try {
      const folder = await createFolder(name);
      setFolders((current) => [
        ...current,
        { ...folder, invoice_count: 0, created_at: new Date().toISOString() },
      ]);
      setFolderId(folder.id);
      setNewFolderName('');
      setShowNewFolder(false);
      // File this session's completed uploads straight into the new folder.
      void onFolderChange(folder.id, folder.name);
    } catch (err) {
      setFolderError(friendlyError(err, 'Could not create the folder.'));
    }
  }, [newFolderName, onFolderChange]);

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
          <p className="muted">PDFs and photos are read, understood, and organised automatically.</p>
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
          aria-label="Upload invoice PDFs or photos"
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
          <strong>Drag &amp; drop PDFs or photos here</strong>
          <div className="muted" style={{ marginTop: '0.25rem' }}>
            or tap to choose, multiple files supported
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf,image/jpeg,image/png,.jpg,.jpeg,.png"
          multiple
          style={{ display: 'none' }}
          onChange={handlePick}
        />

        {/* Destination first: everything uploaded in this batch lands here. */}
        <div className="folder-picker">
          <label className="folder-picker__label" htmlFor="upload-folder">
            Folder
          </label>
          <select
            id="upload-folder"
            className="input"
            value={foldersLoading ? '' : folderId ?? ''}
            disabled={foldersLoading}
            aria-busy={foldersLoading}
            onChange={(e) => void onFolderChange(e.target.value || null)}
          >
            {foldersLoading ? (
              <option value="">Loading folders…</option>
            ) : (
              <>
                <option value="">No folder</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name} ({f.invoice_count})
                  </option>
                ))}
              </>
            )}
          </select>
          {showNewFolder ? (
            <span className="folder-picker__new">
              <input
                className="input"
                placeholder="Folder name"
                value={newFolderName}
                maxLength={60}
                onChange={(e) => setNewFolderName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    void onCreateFolder();
                  }
                }}
                autoFocus
              />
              <button type="button" className="button button--secondary" onClick={() => void onCreateFolder()}>
                Create
              </button>
              <button
                type="button"
                className="button button--secondary"
                onClick={() => {
                  setShowNewFolder(false);
                  setNewFolderName('');
                }}
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              type="button"
              className="linklike"
              onClick={() => setShowNewFolder(true)}
            >
              + New folder
            </button>
          )}
        </div>
        {folderError && <div className="error-banner">{folderError}</div>}

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
                    {/* Done marker: uploaded AND filed where the selector points. */}
                    {(item.phase === 'done' || item.phase === 'flagged') && item.invoiceId && (
                      <div
                        className={`upload-item__folder${item.filing ? ' upload-item__folder--pending' : ''}`}
                        aria-live="polite"
                      >
                        {item.filing
                          ? 'Filing…'
                          : item.folderId
                            ? `✓ Added to ${folders.find((f) => f.id === item.folderId)?.name ?? 'folder'}`
                            : '✓ Uploaded · No folder'}
                      </div>
                    )}
                  </div>
                  <span className={`upload-item__state upload-item__state--${item.phase}`}>
                    {PHASE_LABEL[item.phase]}
                  </span>
                  {item.phase === 'done' && <ConfidenceBadge value={ex?.overall_confidence} />}
                  {ex?.engine === 'gemini' && (
                    <span className="badge badge--primary" title="The AI vision fallback read this document">
                      AI vision
                    </span>
                  )}
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

      {toast && (
        <div className="toast toast--success" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}
