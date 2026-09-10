import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  downloadCsv,
  downloadTallyXml,
  downloadXlsx,
  fetchDigest,
  fetchInvoices,
  friendlyError,
  type InvoiceSummary,
} from '@/lib/api';
import { formatDate, formatINR, statusTone } from '@/lib/format';

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
  const [digest, setDigest] = useState<DigestPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [invoiceList, digestPayload] = await Promise.all([
          fetchInvoices(),
          fetchDigest(7),
        ]);
        setInvoices(invoiceList);
        setDigest(digestPayload as DigestPayload);
      } catch (err) {
        setError(friendlyError(err, 'Failed to load the dashboard.'));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const stats = useMemo(() => {
    const counts: Record<string, number> = {};
    let totalAmount = 0;
    invoices.forEach((invoice) => {
      counts[invoice.status] = (counts[invoice.status] ?? 0) + 1;
      totalAmount += invoice.amount ?? 0;
    });
    return { counts, totalAmount };
  }, [invoices]);

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Your invoices at a glance.</p>
        </div>
        <div className="row-actions" role="group" aria-label="Export invoices">
          {([
            { key: 'csv', label: 'CSV', run: downloadCsv },
            { key: 'xlsx', label: 'Excel', run: downloadXlsx },
            { key: 'tally', label: 'Tally XML', run: downloadTallyXml },
          ] as const).map(({ key, label, run }) => (
            <button
              key={key}
              type="button"
              className="button button--secondary"
              disabled={exporting}
              onClick={async () => {
                setExporting(true);
                try {
                  await run('auto_approved');
                } catch (err) {
                  setError(friendlyError(err, `Could not download the ${label} file.`));
                } finally {
                  setExporting(false);
                }
              }}
            >
              {exporting ? 'Preparing…' : `Export ${label}`}
            </button>
          ))}
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

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
              <span className="muted" style={{ fontSize: '0.85rem' }}>{invoices.length} total</span>
            </div>
            {invoices.length === 0 ? (
              <p className="table-empty">No invoices yet. Upload one to get started.</p>
            ) : (
              <>
                {/* Desktop: table */}
                <div className="table-wrap">
                  <table className="table table--responsive">
                    <thead>
                      <tr>
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
                    <Link key={invoice.id} to={`/app/invoices/${invoice.id}`} className="rowcard">
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
                    </Link>
                  ))}
                </div>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
