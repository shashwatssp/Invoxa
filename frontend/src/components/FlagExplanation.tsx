import { useState } from 'react';
import { explainFlag, friendlyError } from '@/lib/api';

/**
 * "Explain with AI": one bounded AI call that turns the raw flag reasons
 * into a plain-English explanation of what to verify. Purely additive —
 * when AI is unavailable nothing shows beyond the raw reason.
 */
export function FlagExplanation({ invoiceId }: { invoiceId: string }) {
  const [explanation, setExplanation] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (explanation) {
    return (
      <p
        className="muted"
        style={{ fontSize: '0.85rem', margin: '0.5rem 0 0', whiteSpace: 'pre-wrap' }}
      >
        {explanation}
      </p>
    );
  }

  const handleExplain = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await explainFlag(invoiceId);
      if (data.explanation) {
        setExplanation(data.explanation);
      } else {
        setError('AI explanation is unavailable right now — the flag reasons above still apply.');
      }
    } catch (err) {
      setError(friendlyError(err, 'Could not generate an explanation.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginTop: '0.5rem' }}>
      <button type="button" className="linklike" onClick={handleExplain} disabled={loading}>
        {loading ? 'Explaining…' : 'Explain with AI'}
      </button>
      {error && (
        <span className="muted" style={{ fontSize: '0.8rem', marginLeft: '0.5rem' }}>
          {error}
        </span>
      )}
    </div>
  );
}
