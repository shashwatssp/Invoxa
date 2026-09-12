import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  fetchDigest,
  fetchFolders,
  fetchInvoices,
  friendlyError,
  type FolderInfo,
  type InvoiceSummary,
} from '@/lib/api';
import { formatDate, formatINR, statusTone } from '@/lib/format';
import { ExportDialog } from '@/components/ExportDialog';

/** Chip filter values: all, unfiled, or one folder id. */
type FolderScope = 'all' | 'none' | string;

interface DigestPayload {
  window_days?: number;
  generated_at?: string;
  invoices_processed?: number;
  auto_approved?: number;
  flagged_for_review?: number;
  total_amount?: number;
  summary_lines?: string[];
  [k: string]: unknown;
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className={`stat${tone ? ` stat--${tone}` : ''}`}>
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
    </div>
  );
}

export function Dashboard() {
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [digest, setDigest] = useState<DigestPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [folderScope, setFolderScope] = useState<FolderScope>('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [exportOpen, setExportOpen] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [invoiceList, folderList, digestPayload] = await Promise.all([
          fetchInvoices(folderScope === 'all' ? null : folderScope),
          fetchFolders(),
          fetchDigest(7),
        ]);
        setInvoices(invoiceList);
        setFolders(folderList);
        setDigest(digestPayload as DigestPayload);
        // Drop selections that are no longer visible.
        setSelected((current) => {
          const visible = new Set(invoiceList.map((i) => i.id));
          const next = new Set([...current].filter((id) => visible.has(id)));
          return next.size === current.size ? current : next;
        });
      } catch (err) {
        setError(friendlyError(err, 'Failed to load the dashboard.'));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [folderScope]);

  const stats = useMemo(() => {
    const counts: Record<string, number> = {};
    let totalAmount = 0;
    invoices.forEach((invoice) => {
      counts[invoice.status] = (counts[invoice.status] ?? 0) + 1;
      totalAmount += invoice.amount ?? 0;
    });
    return { counts, totalAmount };
  }, [invoices]);

  const allVisibleSelected = invoices.length > 0 && invoices.every((i) => selected.has(i.id));

  const toggleInvoice = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllVisible = () => {
    setSelected((current) => {
      if (invoices.every((i) => current.has(i.id))) {
        const next = new Set(current);
        invoices.forEach((i) => next.delete(i.id));
        return next;
      }
      return new Set(invoices.map((i) => i.id));
    });
  };

  const folderName = (id: string | null) =>
    id ? folders.find((f) => f.id === id)?.name ?? null : null;

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Your invoices at a glance.</p>
        </div>
        <div className="row-actions" role="group" aria-label="Export invoices">
          <button
            type="button"
            className="button button--secondary"
            onClick={() => setExportOpen(true)}
          >
            {selected.size > 0 ? `Export ${selected.size} selected` : 'Export'}
          </button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {!loading && (
        <div className="folder-chips" role="tablist" aria-label="Filter by folder">
          <button
            type="button"
            role="tab"
            aria-selected={folderScope === 'all'}
            className={`pill${folderScope === 'all' ? ' pill--active' : ''}`}
            onClick={() => setFolderScope('all')}
          >
            All
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={folderScope === 'none'}
            className={`pill${folderScope === 'none' ? ' pill--active' : ''}`}
            onClick={() => setFolderScope('none')}
          >
            No folder
          </button>
          {folders.map((folder) => (
            <button
              key={folder.id}
              type="button"
              role="tab"
              aria-selected={folderScope === folder.id}
              className={`pill${folderScope === folder.id ? ' pill--active' : ''}`}
              onClick={() => setFolderScope(folder.id)}
            >
              {folder.name}
              <span className="folder-chip-count">{folder.invoice_count}</span>
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="card">
          <div className="skeleton skeleton-line skeleton-line--w40" />
          <div className="skeleton skeleton-line skeleton-line--w60" />
          <div className="skeleton skeleton-line" />
        </div>
      ) : (
        <>
          <div className="stat-grid">
            <Stat label="Total invoices" value={invoices.length} tone="primary" />
            <Stat label="Auto-approved" value={stats.counts['auto_approved'] ?? 0} tone="success" />
            <Stat label="Needs review" value={stats.counts['flagged'] ?? 0} tone="warning" />
            <Stat label="Total value" value={formatINR(stats.totalAmount)} />
          </div>

          <section className="card" style={{ marginTop: '1rem' }}>
            <div className="card__header">
              <h2>Weekly digest</h2>
              {digest?.generated_at && (
                <span className="badge badge--primary">Last {digest.window_days ?? 7} days</span>
              )}
            </div>
            {digest && Array.isArray(digest.summary_lines) && digest.summary_lines.length > 0 ? (
              <ul className="digest-lines">
                {digest.summary_lines.map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="muted" style={{ margin: 0 }}>No notable activity yet.</p>
            )}
          </section>

          <section className="card">
            <div className="card__header">
              <h2>Invoices</h2>
              <span className="muted" style={{ fontSize: '0.85rem' }}>
                {invoices.length} total
                {selected.size > 0 && ` · ${selected.size} selected`}
              </span>
            </div>
            {invoices.length === 0 ? (
              <p className="table-empty">
                {folderScope === 'all'
                  ? 'No invoices yet. Upload one to get started.'
                  : 'No invoices in this folder yet.'}
              </p>
            ) : (
              <>
                {/* Desktop: table */}
                <div className="table-wrap">
                  <table className="table table--responsive">
                    <thead>
                      <tr>
                        <th>
                          <input
                            type="checkbox"
                            aria-label="Select all visible invoices"
                            checked={allVisibleSelected}
                            onChange={toggleAllVisible}
                          />
                        </th>
                        <th>Invoice #</th>
                        <th>Status</th>
                        <th>Amount</th>
                        <th>Due</th>
                        <th>Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invoices.map((invoice) => (
                        <tr key={invoice.id}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Select ${invoice.invoice_number ?? invoice.id}`}
                              checked={selected.has(invoice.id)}
                              onChange={() => toggleInvoice(invoice.id)}
                            />
                          </td>
                          <td>
                            <Link to={`/app/invoices/${invoice.id}`}>{invoice.invoice_number ?? '(no number)'}</Link>
                          </td>
                          <td>
                            <span className={`badge badge--${statusTone(invoice.status)}`}>
                              {invoice.status.replace('_', ' ')}
                            </span>
                          </td>
                          <td>{formatINR(invoice.amount)}</td>
                          <td>{formatDate(invoice.due_date)}</td>
                          <td>{formatDate(invoice.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {/* Mobile: stacked cards */}
                <div className="table-rowcard">
                  {invoices.map((invoice) => (
                    <div key={invoice.id} className="rowcard rowcard--selectable">
                      <input
                        type="checkbox"
                        className="rowcard__check"
                        aria-label={`Select ${invoice.invoice_number ?? invoice.id}`}
                        checked={selected.has(invoice.id)}
                        onChange={() => toggleInvoice(invoice.id)}
                      />
                      <Link to={`/app/invoices/${invoice.id}`} className="rowcard__link">
                        <div className="rowcard__top">
                          <span className="rowcard__num">{invoice.invoice_number ?? '(no number)'}</span>
                          <span className={`badge badge--${statusTone(invoice.status)}`}>
                            {invoice.status.replace('_', ' ')}
                          </span>
                        </div>
                        <div className="rowcard__meta">
                          <span>{formatINR(invoice.amount)}</span>
                          <span>Due {formatDate(invoice.due_date)}</span>
                        </div>
                        {folderName(invoice.folder_id) && (
                          <div className="rowcard__folder">{folderName(invoice.folder_id)}</div>
                        )}
                      </Link>
                    </div>
                  ))}
                </div>
              </>
            )}
          </section>
        </>
      )}

      <ExportDialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        folders={folders}
        selectedIds={selected.size > 0 ? [...selected] : null}
      />
    </div>
  );
}
