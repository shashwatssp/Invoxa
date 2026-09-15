import { useState, type FormEvent } from 'react';
import {
  askInvoxa,
  draftPaymentChase,
  friendlyError,
  type AskResponse,
  type ChaseResponse,
} from '@/lib/api';

/**
 * Ask Invoxa: natural-language questions answered by the bounded agent.
 * The agent can only read the account's data (whitelisted queries) —
 * it can never modify, send, or delete anything.
 */
export function Ask() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chase, setChase] = useState<ChaseResponse | null>(null);
  const [chaseLoading, setChaseLoading] = useState(false);
  const [chaseError, setChaseError] = useState<string | null>(null);

  const handleAsk = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      const answer = await askInvoxa(trimmed);
      setResult(answer);
    } catch (err) {
      setError(friendlyError(err, 'Could not get an answer. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const handleChase = async () => {
    if (chaseLoading) return;
    setChaseLoading(true);
    setChaseError(null);
    try {
      setChase(await draftPaymentChase());
    } catch (err) {
      setChaseError(friendlyError(err, 'Could not prepare the drafts. Please try again.'));
    } finally {
      setChaseLoading(false);
    }
  };

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>Ask Invoxa</h1>
          <p className="muted">
            Questions about your invoices, answered from your own data. Read-only — the
            assistant can never change, send, or delete anything.
          </p>
        </div>
      </header>

      <form className="card" onSubmit={handleAsk} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Which vendors owe me money this week?"
          maxLength={500}
          aria-label="Your question"
          style={{ flex: '1 1 240px' }}
        />
        <button type="submit" className="button" disabled={loading || !question.trim()}>
          {loading ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {error && <div className="error-banner">{error}</div>}

      {loading && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <div className="skeleton skeleton-line skeleton-line--w60" />
          <div className="skeleton skeleton-line skeleton-line--w40" />
        </div>
      )}

      {result && !loading && (
        <section className="card" style={{ marginTop: '1rem' }}>
          <div className="card__header">
            <h2>Answer</h2>
            {result.model_calls > 0 && (
              <span className="muted" style={{ fontSize: '0.8rem' }}>
                {result.model_calls} AI call{result.model_calls === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{result.answer}</p>
          {result.tool_calls.length > 0 && (
            <p className="muted" style={{ fontSize: '0.8rem', marginBottom: 0, marginTop: '0.75rem' }}>
              Based on: {result.tool_calls.map((call) => call.tool).join(', ')}
            </p>
          )}
        </section>
      )}

      <section className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card__header">
          <h2>Payment reminder drafts</h2>
          <button type="button" className="button button--secondary" onClick={handleChase} disabled={chaseLoading}>
            {chaseLoading ? 'Preparing…' : 'Draft reminders'}
          </button>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: '0.9rem' }}>
          For unpaid invoices due in the next 30 days. Drafts only — nothing is
          sent until you tap a button.
        </p>
        {chaseError && <div className="error-banner" style={{ marginTop: '0.75rem' }}>{chaseError}</div>}
        {chase?.drafts.length === 0 && !chaseError && (
          <p className="muted" style={{ marginTop: '0.75rem' }}>Nothing is due right now. All caught up.</p>
        )}
        {chase?.drafts.map((draft) => (
          <div key={draft.vendor} className="card card--alt" style={{ marginTop: '0.75rem' }}>
            <div className="card__header" style={{ marginBottom: '0.5rem' }}>
              <strong>{draft.vendor}</strong>
              <span className="muted" style={{ fontSize: '0.8rem' }}>
                {draft.invoice_count} invoice{draft.invoice_count === 1 ? '' : 's'}
                {draft.overdue_count > 0 ? ` · ${draft.overdue_count} overdue` : ''}
              </span>
            </div>
            <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{draft.message}</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
              <a className="button button--secondary" href={draft.whatsapp_url} target="_blank" rel="noopener noreferrer">
                Open WhatsApp
              </a>
              <span className="muted" style={{ fontSize: '0.8rem' }}>
                {draft.source === 'gemini' ? 'AI-drafted' : 'template draft'}
              </span>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
