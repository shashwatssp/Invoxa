import { useEffect, useState, type ReactNode } from 'react';
import { fetchHealth } from '@/lib/api';

type HealthState =
  | { phase: 'checking' }
  | { phase: 'healthy' }
  | { phase: 'warming'; message: string }
  | { phase: 'failed'; message: string };

interface HealthGateProps {
  children: ReactNode;
  timeoutMs?: number;
}

/**
 * HealthGate: pings /health on mount. Render-freezes the app during cold starts
 * (Render free tier: 60-90s), keeping the UI inside a warm-up spinner instead
 * of letting it cascade into error toasts.
 */
export function HealthGate({ children, timeoutMs = 65_000 }: HealthGateProps) {
  const [state, setState] = useState<HealthState>({ phase: 'checking' });

  useEffect(() => {
    let cancelled = false;
    const startedAt = Date.now();

    const poll = async () => {
      try {
        const health = await fetchHealth();
        if (cancelled) return;
        if (health?.status === 'ok') {
          setState({ phase: 'healthy' });
          return;
        }
        throw new Error('Unhealthy response');
      } catch (err) {
        if (cancelled) return;
        const elapsed = Date.now() - startedAt;
        if (elapsed >= timeoutMs) {
          setState({
            phase: 'failed',
            message:
              'Backend is taking too long to wake up. Please try again in a minute.',
          });
          return;
        }
        setState({
          phase: 'warming',
          message: 'Warming up backend… this can take up to 90s on the first request.',
        });
        setTimeout(poll, 2_500);
      }
    };

    poll();
    return () => {
      cancelled = true;
    };
  }, [timeoutMs]);

  if (state.phase === 'healthy' || state.phase === 'checking') {
    if (state.phase === 'healthy') return <>{children}</>;
    // Render with spinner on first check (extremely brief)
    return (
      <div className="spinner-page">
        <div className="spinner" />
        <p>Connecting…</p>
      </div>
    );
  }

  if (state.phase === 'warming') {
    return (
      <div className="spinner-page">
        <div className="spinner" />
        <p>{state.message}</p>
      </div>
    );
  }

  return (
    <div className="spinner-page">
      <div className="error-banner">{state.message}</div>
      <button className="button" onClick={() => window.location.reload()}>
        Retry
      </button>
    </div>
  );
}
