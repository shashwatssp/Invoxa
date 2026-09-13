import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  fetchCategorySpend,
  fetchDigest,
  fetchDueSoon,
  fetchFolders,
  fetchInvoices,
  fetchMonthlySpend,
  friendlyError,
  moveInvoicesToFolder,
  type CategorySpendRow,
  type DueSoonItem,
  type FolderInfo,
  type InvoiceSummary,
  type MonthlySpendPoint,
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
  narrative?: string | null;
  narrative_source?: string;
  [k: string]: unknown;
}

/** Client-side render cap for the invoice list; "Show more" adds another page. */
const PAGE_SIZE = 100;

/** Status filter options mirroring the backend InvoiceStatus enum. */
const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'flagged', label: 'Needs review' },
  { value: 'auto_approved', label: 'Auto-approved' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'exported', label: 'Exported' },
];

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  const text = String(value);
  // Long money values (e.g. ₹1,23,141.34) shrink instead of overflowing.
  const long = text.length > 11;
  return (
    <div className={`stat${tone ? ` stat--${tone}` : ''}`}>
      <span className="stat__label">{label}</span>
      <span className={`stat__value${long ? ' stat__value--long' : ''}`} title={text}>
        {text}
      </span>
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

  // List filters: free-text search (debounced), status, upload-date range.
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [hasLoaded, setHasLoaded] = useState(false);
  const [moving, setMoving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [dueSoon, setDueSoon] = useState<DueSoonItem[]>([]);
  const [trend, setTrend] = useState<MonthlySpendPoint[]>([]);
  const [trendMonths, setTrendMonths] = useState<6 | 12>(6);
  const [categorySpend, setCategorySpend] = useState<CategorySpendRow[]>([]);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Transient confirmation (e.g. after a bulk move).
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  // Debounce the search box so typing does not spam the API.
  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [invoiceList, folderList, digestPayload, dueSoonList, trendList, categoryList] = await Promise.all([
        fetchInvoices(folderScope === 'all' ? null : folderScope, {
          search: search || null,
          status: statusFilter || null,
          from: fromDate || null,
          to: toDate || null,
        }),
        fetchFolders(),
        fetchDigest(7),
        fetchDueSoon(5),
        fetchMonthlySpend(6),
        fetchCategorySpend(),
      ]);
      setInvoices(invoiceList);
      setFolders(folderList);
      setDigest(digestPayload as DigestPayload);
      setDueSoon(dueSoonList);
      setTrend(trendList);
      setCategorySpend(categoryList);
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
      setHasLoaded(true);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folderScope, search, statusFilter, fromDate, toDate]);

  // New result set: collapse the list back to the first page.
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [folderScope, search, statusFilter, fromDate, toDate]);

  /** Swap the trend chart between 6 and 12 months without a full reload. */
  const changeTrendMonths = async (months: 6 | 12) => {
    setTrendMonths(months);
    try {
      setTrend(await fetchMonthlySpend(months));
    } catch {
      // The chart keeps its previous data; the next full reload retries.
    }
  };

  const hasActiveFilters = Boolean(search || statusFilter || fromDate || toDate);

  /** File every selected invoice into one folder (null = unfile). */
  const moveSelected = async (folderId: string | null) => {
    if (selected.size === 0 || moving) return;
    setMoving(true);
    try {
      await moveInvoicesToFolder([...selected], folderId);
      const name = folderId
        ? folders.find((f) => f.id === folderId)?.name ?? 'the folder'
        : 'No folder';
      setToast(
        selected.size === 1
          ? `Moved 1 invoice to ${name}.`
          : `Moved ${selected.size} invoices to ${name}.`,
      );
      setSelected(new Set());
      await load();
    } catch (err) {
      setError(friendlyError(err, 'Could not move the invoices.'));
    } finally {
      setMoving(false);
    }
  };

  const clearFilters = () => {
    setSearchInput('');
    setSearch('');
    setStatusFilter('');
    setFromDate('');
    setToDate('');
  };

  const stats = useMemo(() => {
    const counts: Record<string, number> = {};
    let totalAmount = 0;
    invoices.forEach((invoice) => {
      counts[invoice.status] = (counts[invoice.status] ?? 0) + 1;
      totalAmount += invoice.amount ?? 0;
    });
    return { counts, totalAmount };
  }, [invoices]);

  // Pagination: only the first `visibleCount` rows are rendered.
  const visibleInvoices = invoices.slice(0, visibleCount);
  const hiddenCount = invoices.length - visibleInvoices.length;

  const allVisibleSelected = visibleInvoices.length > 0 && visibleInvoices.every((i) => selected.has(i.id));

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
      if (visibleInvoices.every((i) => current.has(i.id))) {
        const next = new Set(current);
        visibleInvoices.forEach((i) => next.delete(i.id));
        return next;
      }
      return new Set(visibleInvoices.map((i) => i.id));
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

      {(
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
          {loading && folders.length === 0
            ? [0, 1, 2].map((i) => (
                <span key={i} className="pill pill--skeleton" aria-hidden />
              ))
            : folders.map((folder) => (
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

      {loading && hasLoaded && (
        <div className="loading-strip" role="status" aria-live="polite">
          <span className="spinner" aria-hidden />
          Loading invoices…
        </div>
      )}

      {loading && !hasLoaded ? (
        <div className="card">
          <div className="skeleton skeleton-line skeleton-line--w40" />
          <div className="skeleton skeleton-line skeleton-line--w60" />
          <div className="skeleton skeleton-line" />
        </div>
      ) : (
        <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.15s ease' }}>
        <>
          <div className="stat-grid">
            <Stat label="Total invoices" value={invoices.length} tone="primary" />
            <Stat label="Auto-approved" value={stats.counts['auto_approved'] ?? 0} tone="success" />
            <Stat label="Needs review" value={stats.counts['flagged'] ?? 0} tone="warning" />
            <Stat label="Total value" value={formatINR(stats.totalAmount)} />
          </div>

          <section className="card due-soon" style={{ marginTop: '1rem' }} aria-label="Due soon">
            <div className="card__header">
              <h2>Due soon</h2>
              <span className="badge badge--medium">Next 5 days + overdue</span>
            </div>
            {dueSoon.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                Nothing due in the next 5 days. You're all caught up.
              </p>
            ) : (
              <ul className="due-soon__list">
                {dueSoon.map((item) => (
                  <li key={item.id}>
                    <Link to={`/app/invoices/${item.id}`}>
                      {item.invoice_number ?? '(no number)'}
                      {item.vendor_name ? ` \u00b7 ${item.vendor_name}` : ''}
                    </Link>
                    <span className="due-soon__amount">{formatINR(item.amount)}</span>
                    {item.overdue && <span className="badge badge--low">Overdue</span>}
                    <span className="muted due-soon__date">Due {formatDate(item.due_date)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card" style={{ marginTop: '1rem' }} aria-label="Monthly spend trend">
            <div className="card__header">
              <h2>Monthly spend</h2>
              <div className="segmented trend-months" role="group" aria-label="Trend range">
                <button
                  type="button"
                  className={`segmented__item${trendMonths === 6 ? ' segmented__item--active' : ''}`}
                  onClick={() => void changeTrendMonths(6)}
                >
                  6M
                </button>
                <button
                  type="button"
                  className={`segmented__item${trendMonths === 12 ? ' segmented__item--active' : ''}`}
                  onClick={() => void changeTrendMonths(12)}
                >
                  12M
                </button>
              </div>
            </div>
            {trend.length > 0 && (
              <div className="trend">
                {trend.map((point) => {
                  const max = Math.max(...trend.map((p) => p.total), 1);
                  const height = Math.max((point.total / max) * 100, point.total > 0 ? 6 : 2);
                  const label = new Date(`${point.month}-01T00:00:00`).toLocaleDateString('en-IN', { month: 'short' });
                  return (
                    <div key={point.month} className="trend__col" title={`${label}: ${formatINR(point.total)} (${point.count} invoices)`}>
                      <div className="trend__bar" style={{ height: `${height}%` }} />
                      <span className="trend__label">{label}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="card" style={{ marginTop: '1rem' }} aria-label="Spend by category">
            <div className="card__header">
              <h2>Spend by category</h2>
              <span className="muted" style={{ fontSize: '0.85rem' }}>All time</span>
            </div>
            {categorySpend.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                No categorized spend yet. Categories are assigned automatically
                (or by you) on the invoice detail page.
              </p>
            ) : (
              <ul className="catspend">
                {categorySpend.map((row) => {
                  const max = Math.max(...categorySpend.map((r) => r.total_spend), 1);
                  const width = Math.max((row.total_spend / max) * 100, 2);
                  return (
                    <li key={row.category} className="catspend__row">
                      <span className="catspend__label">{row.category.replace('_', ' ')}</span>
                      <span className="catspend__bar-wrap">
                        <span className="catspend__bar" style={{ width: `${width}%` }} />
                      </span>
                      <span className="catspend__amount">{formatINR(row.total_spend)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="card" style={{ marginTop: '1rem' }}>
            <div className="card__header">
              <h2>Weekly digest</h2>
              {digest?.generated_at && (
                <span className="badge badge--primary">Last {digest.window_days ?? 7} days</span>
              )}
            </div>
            {digest?.narrative && (
              <p className="digest-narrative">
                {digest.narrative}
                {digest.narrative_source === 'gemini' && (
                  <span className="badge badge--primary digest-narrative__badge">AI</span>
                )}
              </p>
            )}
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
              <div className="row-actions" style={{ alignItems: 'center' }}>
                {selected.size > 0 && (
                  <select
                    className="input"
                    style={{ width: 'auto', minHeight: '2.4rem', fontSize: '0.85rem' }}
                    aria-label="Move selected invoices to folder"
                    value=""
                    disabled={moving}
                    onChange={(e) => {
                      const value = e.target.value;
                      void moveSelected(value === 'none' ? null : value || null);
                      e.currentTarget.value = '';
                    }}
                  >
                    <option value="">{moving ? 'Moving…' : 'Move to folder…'}</option>
                    <option value="none">No folder</option>
                    {folders.map((f) => (
                      <option key={f.id} value={f.id}>{f.name}</option>
                    ))}
                  </select>
                )}
                <span className="muted" style={{ fontSize: '0.85rem' }}>
                  {invoices.length} total
                  {selected.size > 0 && ` · ${selected.size} selected`}
                </span>
              </div>
            </div>
            <div className="filter-bar" role="search" aria-label="Filter invoices">
              <input
                type="search"
                className="input filter-bar__search"
                placeholder="Search invoice # or vendor"
                aria-label="Search invoice number or vendor"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
              <select
                className="input filter-bar__status"
                aria-label="Filter by status"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All statuses</option>
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <label className="filter-bar__field">
                <span className="filter-bar__label">From</span>
                <span className="date-wrap">
                  {!fromDate && <span className="date-wrap__hint" aria-hidden>Choose date</span>}
                  <input
                    type="date"
                    className={`input filter-bar__date${fromDate ? '' : ' date-wrap--empty'}`}
                    aria-label="Uploaded from"
                    value={fromDate}
                    onChange={(e) => setFromDate(e.target.value)}
                  />
                </span>
              </label>
              <label className="filter-bar__field">
                <span className="filter-bar__label">To</span>
                <span className="date-wrap">
                  {!toDate && <span className="date-wrap__hint" aria-hidden>Choose date</span>}
                  <input
                    type="date"
                    className={`input filter-bar__date${toDate ? '' : ' date-wrap--empty'}`}
                    aria-label="Uploaded to"
                    value={toDate}
                    onChange={(e) => setToDate(e.target.value)}
                  />
                </span>
              </label>
              {hasActiveFilters && (
                <button
                  type="button"
                  className="button button--secondary button--small filter-bar__clear"
                  onClick={clearFilters}
                >
                  Clear
                </button>
              )}
            </div>
            {invoices.length === 0 ? (
              <div className="table-empty">
                {hasActiveFilters ? (
                  'No invoices match your filters.'
                ) : folderScope === 'all' ? (
                  <>
                    <p style={{ margin: '0 0 1rem' }}>
                      No invoices yet. Upload your first one and Invoxa will
                      read, check, and organise it automatically.
                    </p>
                    <Link className="button" to="/app/upload">
                      Upload your first invoice
                    </Link>
                  </>
                ) : (
                  <p style={{ margin: 0 }}>No invoices in this folder yet.</p>
                )}
              </div>
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
                        <th>Vendor</th>
                        <th>Status</th>
                        <th>Amount</th>
                        <th>Due</th>
                        <th>Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleInvoices.map((invoice) => (
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
                          <td>{invoice.vendor_name ?? '\u2014'}</td>
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
                  {visibleInvoices.map((invoice) => (
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
                          <span>{invoice.vendor_name ?? '\u2014'}</span>
                          <span>{formatINR(invoice.amount)}</span>
                        </div>
                        <div className="rowcard__meta">
                          <span>Due {formatDate(invoice.due_date)}</span>
                        </div>
                        {folderName(invoice.folder_id) && (
                          <div className="rowcard__folder">{folderName(invoice.folder_id)}</div>
                        )}
                      </Link>
                    </div>
                  ))}
                </div>
                {hiddenCount > 0 && (
                  <div className="show-more">
                    <span className="muted">
                      Showing {visibleInvoices.length} of {invoices.length} invoices
                    </span>
                    <button
                      type="button"
                      className="button button--secondary"
                      onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
                    >
                      Show {Math.min(hiddenCount, PAGE_SIZE)} more
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        </>
        </div>
      )}

      <ExportDialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        folders={folders}
        selectedIds={selected.size > 0 ? [...selected] : null}
      />

      {toast && (
        <div className="toast toast--success" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}
