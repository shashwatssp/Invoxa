import { useEffect, useMemo, useState } from 'react';
import {
  buildCsvDownloadUrl,
  fetchDigest,
  fetchInvoices,
  type InvoiceSummary,
} from '@/lib/api';
import { formatDate, formatINR } from '@/lib/format';

interface DigestPayload {
  window_days?: number;
  invoices_processed?: number;
  auto_approved?: number;
  flagged_for_review?: number;
  total_amount?: number;
  summary_lines?: string[];
  [k: string]: unknown;
}

export function Dashboard() {
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [digest, setDigest] = useState<DigestPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const totals = useMemo(() => {
    const counts: Record<string, number> = {};
    invoices.forEach((invoice) => {
      counts[invoice.status] = (counts[invoice.status] ?? 0) + 1;
    });
    const totalAmount = invoices.reduce((sum, invoice) => sum + (invoice.amount ?? 0), 0);
    return { counts, totalAmount };
  }, [invoices]);

  return (
    <div>
      <section className="card">
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>Dashboard</h2>
          <a
            className="button"
            href={buildCsvDownloadUrl('auto_approved')}
            download
          >
            Download Tally/Zoho CSV
          </a>
        </header>
        {error && <div className="error-banner" style={{ marginTop: '0.75rem' }}>{error}</div>}
        {loading ? (
          <div className="spinner-page"><div className="spinner" /><p>Loading…</p></div>
        ) : (
          <div className="field-grid" style={{ marginTop: '0.75rem' }}>
            {Object.entries(totals.counts).map(([status, count]) => (
              <div key={status} className="field">
                <span className="field__label">{status.replace('_', ' ')}</span>
                <span className="field__value">{count}</span>
              </div>
            ))}
            <div className="field">
              <span className="field__label">Total amount</span>
              <span className="field__value">{formatINR(totals.totalAmount)}</span>
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Weekly digest</h2>
        {!digest ? (
          <p className="muted">Loading…</p>
        ) : (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              Last {digest.window_days ?? 7} days
              {' '}({formatDate(digest.generated_at as string)})
            </p>
            {Array.isArray(digest.summary_lines) && digest.summary_lines.length > 0 ? (
              <ul style={{ paddingLeft: '1.2rem' }}>
                {digest.summary_lines.map((line, index) => (
                  <li key={index} className="muted">{line}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">No notable activity yet.</p>
            )}
          </>
        )}
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Invoices</h2>
        {invoices.length === 0 ? (
          <p className="table-empty">No invoices yet. Upload one to get started.</p>
        ) : (
          <table className="table">
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
                  <td>{invoice.invoice_number ?? '-'}</td>
                  <td>
                    <span className="badge">{invoice.status}</span>
                  </td>
                  <td>{formatINR(invoice.amount)}</td>
                  <td>{formatDate(invoice.due_date)}</td>
                  <td>{formatDate(invoice.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
