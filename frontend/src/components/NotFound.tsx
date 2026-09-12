import { Link } from 'react-router-dom';

/** Shown for any URL that does not match a route. */
export function NotFound({ inApp = false }: { inApp?: boolean }) {
  return (
    <div className="card" style={{ textAlign: 'center', padding: '3rem 1.25rem' }}>
      <h1 style={{ fontSize: '2.5rem', marginBottom: '0.25rem' }}>404</h1>
      <p className="muted" style={{ margin: '0 0 1.25rem' }}>
        That page doesn't exist. It may have been moved or the link is wrong.
      </p>
      <Link className="button" to={inApp ? '/app' : '/'}>
        {inApp ? 'Back to dashboard' : 'Back to home'}
      </Link>
    </div>
  );
}
