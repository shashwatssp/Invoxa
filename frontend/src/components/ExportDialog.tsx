import { useEffect, useMemo, useRef, useState } from 'react';
import {
  downloadCsv,
  downloadGstSummaryCsv,
  downloadStatementPdf,
  downloadTallyXml,
  downloadXlsx,
  friendlyError,
  previewExport,
  type ExportFilters,
  type FolderInfo,
} from '@/lib/api';
import { formatINR } from '@/lib/format';
import {
  describeRange,
  resolvePeriod,
  type CustomPeriod,
  type CustomUnit,
  type PeriodPreset,
} from '@/lib/period';

type ExportFormat = 'csv' | 'xlsx' | 'tally' | 'pdf' | 'gst';

const FORMATS: { key: ExportFormat; label: string }[] = [
  { key: 'csv', label: 'CSV' },
  { key: 'xlsx', label: 'Excel' },
  { key: 'tally', label: 'Tally XML' },
  { key: 'pdf', label: 'PDF' },
  { key: 'gst', label: 'GST summary' },
];

const PRESETS: { key: PeriodPreset; label: string }[] = [
  { key: '7d', label: 'Last 7 days' },
  { key: '14d', label: 'Last 14 days' },
  { key: 'this_month', label: 'This month' },
  { key: 'last_month', label: 'Last month' },
  { key: 'everything', label: 'Everything' },
  { key: 'custom', label: 'Custom' },
];

const STATUS_OPTIONS: { key: string | null; label: string }[] = [
  { key: 'auto_approved', label: 'Auto-approved' },
  { key: 'reviewed', label: 'Reviewed' },
  { key: null, label: 'All statuses' },
];

interface ExportDialogProps {
  open: boolean;
  onClose: () => void;
  folders: FolderInfo[];
  /** When exporting selected invoices, their ids (period/folder are ignored). */
  selectedIds: string[] | null;
}

export function ExportDialog({ open, onClose, folders, selectedIds }: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>('csv');
  const [preset, setPreset] = useState<PeriodPreset>('this_month');
  const [custom, setCustom] = useState<CustomPeriod>({ count: 1, unit: 'days' });
  const [status, setStatus] = useState<string | null>('auto_approved');
  const [folderId, setFolderId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ count: number; total: number } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const range = useMemo(() => resolvePeriod(preset, custom), [preset, custom]);
  const rangeLabel = describeRange(range);

  const filters: ExportFilters = useMemo(
    () => ({
      status,
      from: range.from,
      to: range.to,
      folderId: folderId || null,
      ids: selectedIds ?? null,
    }),
    [status, range, folderId, selectedIds],
  );

  // Live preview of what the export will contain (skipped while exporting).
  useEffect(() => {
    if (!open || exporting) return;
    let alive = true;
    setPreviewLoading(true);
    previewExport(filters)
      .then((p) => {
        if (alive) setPreview({ count: p.count, total: p.total });
      })
      .catch(() => {
        if (alive) setPreview(null);
      })
      .finally(() => {
        if (alive) setPreviewLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, exporting, filters]);

  // ESC closes while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const download = async () => {
    setExporting(true);
    setError(null);
    try {
      if (format === 'csv') await downloadCsv(filters);
      else if (format === 'xlsx') await downloadXlsx(filters);
      else if (format === 'tally') await downloadTallyXml(filters);
      else if (format === 'gst') await downloadGstSummaryCsv(filters);
      else await downloadStatementPdf(filters);
      onClose();
    } catch (err) {
      setError(friendlyError(err, 'Could not generate the export. Please try again.'));
    } finally {
      setExporting(false);
    }
  };

  const formatLabel = FORMATS.find((f) => f.key === format)?.label ?? format;

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
        aria-label="Export invoices"
        ref={panelRef}
      >
        <div className="export-panel__handle" aria-hidden />
        <div className="export-panel__header">
          <h2>Export invoices</h2>
          <button type="button" className="linklike" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="export-panel__body">
          {selectedIds && (
            <div className="export-locked">
              {selectedIds.length} selected invoice{selectedIds.length === 1 ? '' : 's'}
              <span className="muted"> (period and folder filters are ignored)</span>
            </div>
          )}

          <fieldset className="export-fieldset">
            <legend>Format</legend>
            <div className="segmented" role="group" aria-label="Export format">
              {FORMATS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className={`segmented__item${format === f.key ? ' segmented__item--active' : ''}`}
                  onClick={() => setFormat(f.key)}
                  disabled={exporting}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </fieldset>

          {!selectedIds && (
            <>
              <fieldset className="export-fieldset">
                <legend>Period</legend>
                <div className="pill-row" role="group" aria-label="Period">
                  {PRESETS.map((p) => (
                    <button
                      key={p.key}
                      type="button"
                      className={`pill${preset === p.key ? ' pill--active' : ''}`}
                      onClick={() => setPreset(p.key)}
                      disabled={exporting}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                {preset === 'custom' && (
                  <div className="custom-period">
                    <label className="custom-period__stepper">
                      Last
                      <input
                        type="number"
                        min={1}
                        max={365}
                        value={custom.count}
                        onChange={(e) =>
                          setCustom((c) => ({ ...c, count: Number(e.target.value) || 1 }))
                        }
                        disabled={exporting}
                      />
                      <select
                        value={custom.unit}
                        onChange={(e) =>
                          setCustom((c) => ({ ...c, unit: e.target.value as CustomUnit }))
                        }
                        disabled={exporting}
                      >
                        <option value="days">days</option>
                        <option value="weeks">weeks</option>
                        <option value="months">months</option>
                      </select>
                    </label>
                    <span className="muted">or set exact dates:</span>
                    <input
                      type="date"
                      aria-label="From date"
                      value={custom.from ?? ''}
                      onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value || null }))}
                      disabled={exporting}
                    />
                    <input
                      type="date"
                      aria-label="To date"
                      value={custom.to ?? ''}
                      onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value || null }))}
                      disabled={exporting}
                    />
                  </div>
                )}
                <div className="export-range-caption muted">{rangeLabel}</div>
              </fieldset>

              <fieldset className="export-fieldset">
                <legend>Status</legend>
                <div className="pill-row" role="group" aria-label="Status">
                  {STATUS_OPTIONS.map((s) => (
                    <button
                      key={s.label}
                      type="button"
                      className={`pill${status === s.key ? ' pill--active' : ''}`}
                      onClick={() => setStatus(s.key)}
                      disabled={exporting}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {folders.length > 0 && (
                <fieldset className="export-fieldset">
                  <legend>Folder</legend>
                  <select
                    className="input"
                    value={folderId ?? ''}
                    onChange={(e) => setFolderId(e.target.value || null)}
                    disabled={exporting}
                  >
                    <option value="">All folders</option>
                    <option value="none">No folder</option>
                    {folders.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                </fieldset>
              )}
            </>
          )}

          <div className="export-preview" aria-live="polite">
            {previewLoading ? (
              <span className="skeleton skeleton-line" style={{ width: '10rem' }} />
            ) : preview ? (
              <>
                {preview.count} invoice{preview.count === 1 ? '' : 's'} ·{' '}
                {formatINR(preview.total)}
              </>
            ) : (
              <span className="muted">Preview unavailable — the download will still work.</span>
            )}
          </div>

          {error && <div className="error-banner">{error}</div>}
        </div>

        <div className="export-panel__footer">
          <button
            type="button"
            className="button"
            onClick={download}
            disabled={exporting}
          >
            {exporting ? 'Preparing…' : `Download ${formatLabel}`}
          </button>
        </div>
      </div>
    </div>
  );
}
