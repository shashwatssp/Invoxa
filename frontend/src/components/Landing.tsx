import { Link } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';

const FEATURES = [
  {
    title: 'Snap in any receipt',
    body: 'Drop PDFs straight from your inbox or scanner. Multiple files at once, progress on every one.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
      </svg>
    ),
  },
  {
    title: 'Fields read themselves',
    body: 'Vendor, GSTIN, invoice number, dates and totals are extracted automatically, with a confidence score on every field.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /><path d="m9 15 2 2 4-4" />
      </svg>
    ),
  },
  {
    title: 'Approve with eyes open',
    body: 'Flagged receipts go to a review queue where approvers open the original document side by side. No blind approvals, ever.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" />
      </svg>
    ),
  },
  {
    title: 'Books-ready exports',
    body: 'Approved receipts export to CSV, Excel or Tally-ready XML — your accountant imports them without rework.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M3 3v16a2 2 0 0 0 2 2h16" /><path d="m7 13 3-3 4 4 5-5" />
      </svg>
    ),
  },
];

export function Landing() {
  const { status } = useAuth();

  return (
    <div className="landing">
      <header className="landing__nav">
        <span className="app-nav__brand landing__brand">
          <span className="app-nav__brand-mark" aria-hidden>i</span>
          Invoxa
        </span>
        <nav className="landing__nav-actions" aria-busy={status === 'loading'}>
          {status === 'loading' ? (
            // Restoring the session: reserve the nav space instead of flashing
            // the logged-out links before switching to "Open app".
            <span className="landing__nav-skeleton skeleton" aria-hidden="true" />
          ) : status === 'authenticated' ? (
            <Link to="/app" className="button button--secondary">Open app</Link>
          ) : (
            <>
              <Link to="/login" className="landing__nav-login">Log in</Link>
              <Link to="/signup" className="button">Get started free</Link>
            </>
          )}
        </nav>
      </header>

      <main className="landing__hero">
        <span className="landing__eyebrow">Receipt automation for Indian micro-SMEs</span>
        <h1 className="landing__title">
          Stop typing invoices.
          <br />
          <span className="landing__title-accent">Start trusting your books.</span>
        </h1>
        <p className="landing__subtitle">
          Upload a receipt, and Invoxa reads the vendor, GSTIN, dates and totals for you.
          Anything uncertain goes to a human review queue, with the original document
          one click away, so your books stay fast <em>and</em> accurate.
        </p>
        <div className="landing__cta">
          <Link to="/signup" className="button button--large">Create your free account</Link>
          <Link to="/login" className="button button--secondary button--large">I already have one</Link>
        </div>
        <div className="landing__proof muted">
          Takes under a minute &middot; No card required
        </div>
      </main>

      <section className="landing__features" aria-label="What you get">
        {FEATURES.map((feature) => (
          <article key={feature.title} className="card landing__feature">
            <span className="landing__feature-icon" aria-hidden>{feature.icon}</span>
            <h3>{feature.title}</h3>
            <p>{feature.body}</p>
          </article>
        ))}
      </section>

      <footer className="landing__footer muted">
        Invoxa: your receipts, processed.
      </footer>
    </div>
  );
}
