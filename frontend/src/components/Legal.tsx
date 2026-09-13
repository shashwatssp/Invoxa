import { Link } from 'react-router-dom';

function LegalShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ maxWidth: '46rem', margin: '0 auto', padding: '2rem 1.25rem 4rem' }}>
      <h1 style={{ marginBottom: '0.25rem' }}>{title}</h1>
      <p className="muted" style={{ marginTop: 0 }}>Last updated: 12 September 2026</p>
      <div className="card" style={{ marginTop: '1rem', lineHeight: 1.65 }}>
        {children}
      </div>
      <p style={{ marginTop: '1.25rem' }}>
        <Link to="/">Back to home</Link>
      </p>
    </div>
  );
}

export function Terms() {
  return (
    <LegalShell title="Terms of Service">
      <p>
        Invoxa is a bookkeeping assistant for Indian micro-businesses. By
        creating an account you agree to the terms below.
      </p>
      <p>
        <strong>1. Your account.</strong> You are responsible for the activity
        in your account and for keeping your password safe. One account per
        business; anything you upload belongs to you.
      </p>
      <p>
        <strong>2. Your data.</strong> You own your invoices and everything
        extracted from them. Invoxa never sells your data and never executes
        payments or filings on its own \u2014 a human approves before anything
        leaves the system.
      </p>
      <p>
        <strong>3. Accuracy.</strong> Extraction is confidence-scored, and
        low-confidence or inconsistent documents are flagged for your review.
        Invoxa is a assistant, not an accountant: you remain responsible for
        your books and for anything you export or file.
      </p>
      <p>
        <strong>4. Service availability.</strong> The service is offered
        as-is. We aim for high availability but do not promise uninterrupted
        operation.
      </p>
      <p>
        <strong>5. Changes.</strong> We may update these terms; material
        changes will be announced in the app.
      </p>
    </LegalShell>
  );
}

export function Privacy() {
  return (
    <LegalShell title="Privacy Policy">
      <p>
        <strong>What we store.</strong> Your account email, the invoice files
        you upload, and the fields extracted from them (vendor, numbers,
        dates, category). Everything is stored in your own Supabase project
        and scoped strictly to your account.
      </p>
      <p>
        <strong>What we do not store.</strong> We never store payment
        credentials. We never sell or share your data with advertisers.
      </p>
      <p>
        <strong>AI processing.</strong> When enabled, difficult documents
        (scans, photos) and weekly summaries are processed by Google's
        Gemini API on our server side. Only the invoice content needed for
        the task is sent; your API keys and credentials are never sent. AI
        output is always checked by deterministic rules before it reaches
        your books.
      </p>
      <p>
        <strong>Deleting your data.</strong> Deleting an invoice removes it,
        its receipt file, and its review entries. Contact support to delete
        your whole account.
      </p>
      <p>
        <strong>Questions?</strong> Reach us from the app's Account page.
      </p>
    </LegalShell>
  );
}
