import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  fetchInvoices,
  fetchVendorSummaryPdf,
  fetchVendorsSummary,
  friendlyError,
  shareOrDownloadPdf,
  type InvoiceSummary,
  type VendorSummary,
} from '@/lib/api';
import { formatDate, formatINR, statusTone } from '@/lib/format';

/** Build the plain-text summary shared to WhatsApp (all or one vendor). */
function buildShareText(summary: VendorSummary[], vendor?: string): string {
  const rows = vendor ? summary.filter((row) => row.vendor === vendor) : summary.slice(0, 10);
  const title = vendor ? `Invoxa vendor summary: ${vendor}` : 'Invoxa vendor spend summary';
  const lines = rows.map((row) => {
    const spend = formatINR(row.total_spend);
    return `\u2022 ${row.vendor}: ${spend} (${row.invoice_count} invoice${row.invoice_count === 1 ? '' : 's'})`;
  });
  return `${title}\n${lines.join('\n')}`;
}

export function Vendors() {
  const [summary, setSummary] = useState<VendorSummary[]>([]);
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const [shareMenuOpen, setShareMenuOpen] = useState(false);
  const shareMenuRef = useRef<HTMLDivElement | null>(null);

  // Close the share menu on Escape or on any click outside it.
  useEffect(() => {
    if (!shareMenuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShareMenuOpen(false);
    };
    const onClick = (e: MouseEvent) => {
      if (shareMenuRef.current && !shareMenuRef.current.contains(e.target as Node)) {
        setShareMenuOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onClick);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onClick);
    };
  }, [shareMenuOpen]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [vendorSummary, invoiceList] = await Promise.all([
          fetchVendorsSummary(),
          fetchInvoices(),
        ]);
        setSummary(vendorSummary);
        setInvoices(invoiceList);
      } catch (err) {
        setError(friendlyError(err, 'Could not load the vendor summary.'));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const shareViaWhatsApp = (vendor?: string) => {
    const url = `https://wa.me/?text=${encodeURIComponent(buildShareText(summary, vendor))}`;
    window.open(url, '_blank', 'noopener');
  };

  const shareAsPdf = async () => {
    setSharing(true);
    try {
      const blob = await fetchVendorSummaryPdf();
      await shareOrDownloadPdf(blob, 'invoxa_vendors.pdf', 'Invoxa vendor spend summary');
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        setError(friendlyError(err, 'Could not share the summary.'));
      }
    } finally {
      setSharing(false);
    }
  };

  const invoicesFor = (vendor: string): InvoiceSummary[] =>
    invoices.filter((inv) => (inv.vendor_name ?? '(unknown)') === vendor);

  const totalSpend = summary.reduce((sum, row) => sum + row.total_spend, 0);

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>Vendors</h1>
          <p className="muted">Where the money goes, vendor by vendor.</p>
        </div>
        {!loading && summary.length > 0 && (
          <div className="share-menu" ref={shareMenuRef}>
            <button
              type="button"
              className="button button--secondary"
              aria-haspopup="menu"
              aria-expanded={shareMenuOpen}
              onClick={() => setShareMenuOpen((open) => !open)}
            >
              Share ▾
            </button>
            {shareMenuOpen && (
              <div className="share-menu__popover" role="menu" aria-label="Share the vendor summary">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setShareMenuOpen(false);
                    shareViaWhatsApp();
                  }}
                >
                  Text message
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setShareMenuOpen(false);
                    void shareAsPdf();
                  }}
                  disabled={sharing}
                >
                  {sharing ? 'Preparing…' : 'PDF file'}
                </button>
              </div>
            )}
          </div>
        )}
      </header>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="card">
          <div className="skeleton skeleton-line skeleton-line--w60" />
          <div className="skeleton skeleton-line skeleton-line--w40" />
        </div>
      ) : summary.length === 0 ? (
        <div className="card">
          <p className="table-empty">No vendors yet. Upload invoices to see spend per vendor.</p>
        </div>
      ) : (
        <section className="card">
          <div className="card__header">
            <h2>Spend by vendor</h2>
            <span className="muted" style={{ fontSize: '0.85rem' }}>
              {summary.length} vendor{summary.length === 1 ? '' : 's'} · {formatINR(totalSpend)} total
            </span>
          </div>
          {/* Desktop: table with expandable rows */}
          <div className="table-wrap">
            <table className="table table--responsive">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Invoices</th>
                  <th>Total spend</th>
                  <th>Last invoice</th>
                  <th aria-label="Share" />
                </tr>
              </thead>
              <tbody>
                {summary.map((row) => {
                  const open = expanded === row.vendor;
                  return (
                    <VendorRow
                      key={row.vendor}
                      row={row}
                      open={open}
                      onToggle={() => setExpanded(open ? null : row.vendor)}
                      onShare={() => shareViaWhatsApp(row.vendor)}
                      invoices={invoicesFor(row.vendor)}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
          {/* Mobile: stacked cards with expandable details */}
          <div className="table-rowcard">
            {summary.map((row) => {
              const open = expanded === row.vendor;
              return (
                <div key={row.vendor} className="rowcard">
                  <button type="button" className="vendors-card__head" onClick={() => setExpanded(open ? null : row.vendor)}>
                    <span className="rowcard__num">{row.vendor}</span>
                    <span>{formatINR(row.total_spend)}</span>
                  </button>
                  <div className="rowcard__meta">
                    <span>{row.invoice_count} invoice{row.invoice_count === 1 ? '' : 's'}</span>
                    <span>{row.last_invoice ? `Last ${formatDate(row.last_invoice)}` : ''}</span>
                  </div>
                  <div className="vendors-card__actions">
                    <button type="button" className="linklike" onClick={() => setExpanded(open ? null : row.vendor)}>
                      {open ? 'Hide invoices' : 'View invoices'}
                    </button>
                    <button type="button" className="linklike" onClick={() => shareViaWhatsApp(row.vendor)}>
                      Share
                    </button>
                  </div>
                  {open && <VendorDetail invoices={invoicesFor(row.vendor)} />}
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

function VendorRow({
  row,
  open,
  onToggle,
  onShare,
  invoices,
}: {
  row: VendorSummary;
  open: boolean;
  onToggle: () => void;
  onShare: () => void;
  invoices: InvoiceSummary[];
}) {
  return (
    <>
      <tr className="vendors-row" onClick={onToggle}>
        <td>
          <button type="button" className="vendors-row__toggle linklike">
            {open ? '▾' : '▸'} {row.vendor}
          </button>
        </td>
        <td>{row.invoice_count}</td>
        <td>{formatINR(row.total_spend)}</td>
        <td>{row.last_invoice ? formatDate(row.last_invoice) : '\u2014'}</td>
        <td>
          <button
            type="button"
            className="linklike"
            onClick={(e) => {
              e.stopPropagation();
              onShare();
            }}
            title={`Share ${row.vendor}'s summary on WhatsApp`}
          >
            Share
          </button>
        </td>
      </tr>
      {open && (
        <tr className="vendors-detail">
          <td colSpan={5}>
            <VendorDetail invoices={invoices} />
          </td>
        </tr>
      )}
    </>
  );
}

function VendorDetail({ invoices }: { invoices: InvoiceSummary[] }) {
  if (invoices.length === 0) {
    return <p className="muted" style={{ margin: '0.25rem 0 0.5rem', fontSize: '0.85rem' }}>No invoices found.</p>;
  }
  return (
    <div className="vendors-detail__list">
      {invoices.map((inv) => (
        <div key={inv.id} className="vendors-detail__item">
          <Link to={`/app/invoices/${inv.id}`}>
            {inv.invoice_number ?? '(no number)'}
          </Link>
          <span className={`badge badge--${statusTone(inv.status)}`}>
            {inv.status.replace('_', ' ')}
          </span>
          <span className="vendors-detail__amount">{formatINR(inv.amount)}</span>
          <span className="muted">{formatDate(inv.created_at)}</span>
        </div>
      ))}
    </div>
  );
}
