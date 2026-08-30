import { useCallback, useRef, useState, type DragEvent, type ChangeEvent } from 'react';
import { api } from '@/lib/api';

interface UploadResult {
  id: string;
  status: string;
  filename: string;
}

type Phase = 'idle' | 'uploading' | 'success' | 'error';

export function Upload() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [active, setActive] = useState(false);

  const onFile = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setPhase('uploading');
    try {
      const form = new FormData();
      form.append('file', file, file.name);
      const { data } = await api.post<{ id: string; extraction?: { needs_review?: boolean } }>(
        '/api/invoices/upload',
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      setResult({
        id: data.id,
        status: data.extraction?.needs_review ? 'flagged' : 'auto_approved',
        filename: file.name,
      });
      setPhase('success');
    } catch (err) {
      setPhase('error');
      setError(err instanceof Error ? err.message : 'Upload failed');
    }
  }, []);

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void onFile(file);
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setActive(true);
  };

  const handleDragLeave = () => setActive(false);

  const handlePick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void onFile(file);
  };

  return (
    <section className="card">
      <h2 style={{ marginTop: 0 }}>Upload invoice</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Drop a PDF here. The backend stores it in Supabase and runs the extraction pipeline.
      </p>
      <div
        className={`dropzone${active ? ' dropzone--active' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            inputRef.current?.click();
          }
        }}
      >
        {phase === 'uploading' && 'Uploading…'}
        {(phase === 'idle' || phase === 'success' || phase === 'error') && (
          <span>
            <strong>Drag &amp; drop</strong> or <u>click to choose</u> a PDF.
          </span>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        style={{ display: 'none' }}
        onChange={handlePick}
      />

      {error && <div className="error-banner" style={{ marginTop: '0.75rem' }}>{error}</div>}

      {result && (
        <div className="card" style={{ marginTop: '0.75rem', background: 'var(--color-bg)' }}>
          <div><strong>{result.filename}</strong></div>
          <div className="muted">Invoice id: {result.id}</div>
          <div>
            Status: <span className={result.status === 'auto_approved' ? 'badge badge--high' : 'badge badge--low'}>
              {result.status}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
