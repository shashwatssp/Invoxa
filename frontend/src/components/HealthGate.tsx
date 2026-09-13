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
 * (serverless backends idle between requests; cold starts are brief, not
 * minutes), keeping the UI inside a warm-up spinner instead
 * of letting it cascade into error toasts.
 */
const DEFAULT_TIMEOUT = 65_000;
const LOCAL_TIMEOUT = 10_000;

export function HealthGate({ children, timeoutMs }: HealthGateProps) {
  // When running locally (no VITE_API_BASE_URL), the backend is a direct
  // localhost process, so there is no cold start. Use a shorter timeout and a message
  // that helps the user diagnose a missing service.
  const isLocal = !import.meta.env.VITE_API_BASE_URL;
  const effectiveTimeout = timeoutMs ?? (isLocal ? LOCAL_TIMEOUT : DEFAULT_TIMEOUT);
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
        if (elapsed >= effectiveTimeout) {
          setState({
            phase: 'failed',
            message: isLocal
              ? 'Backend is not reachable. Start it with: cd backend && uvicorn app.main:app --reload --port 8000'
              : 'Backend is taking too long to wake up. Please try again in a minute.',
          });
          return;
        }
        setState({
          phase: 'warming',
          message: isLocal
            ? 'Connecting to backend…'
            : 'Warming up backend… this can take up to 90s on the first request.',
        });
        setTimeout(poll, 2_500);
      }
    };

    poll();
    return () => {
      cancelled = true;
    };
  }, [effectiveTimeout, isLocal]);

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
