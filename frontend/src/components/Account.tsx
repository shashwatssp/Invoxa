import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { applyThemePreference, getThemePreference, type ThemePreference } from '@/lib/theme';

/** Profile + session: the one place that always offers Sign out,
 * including on phones where the top nav is hidden. */
export function Account() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleSignOut = () => {
    logout();
    navigate('/', { replace: true });
  };

  const initial = (user?.name || user?.email || '?').trim().charAt(0).toUpperCase();

  return (
    <div>
      <header className="page-head">
        <div>
          <h1>Account</h1>
          <p className="muted">Your profile and session.</p>
        </div>
      </header>

      <section className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span className="avatar" aria-hidden>{initial}</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 600 }}>{user?.name || 'Invoxa user'}</div>
            <div className="muted" style={{ fontSize: '0.88rem', overflowWrap: 'anywhere' }}>
              {user?.email}
            </div>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card__header">
          <h2>Appearance</h2>
        </div>
        <ThemePicker />
      </section>

      <section className="card">
        <div className="card__header">
          <h2>Session</h2>
        </div>
        <p className="muted" style={{ margin: '0 0 1rem', fontSize: '0.9rem' }}>
          Signing out returns you to the landing page. Your invoices stay
          safely in your account.
        </p>
        <button type="button" className="button button--danger" onClick={handleSignOut}>
          Sign out
        </button>
      </section>
    </div>
  );
}

const THEME_OPTIONS: { key: ThemePreference; label: string }[] = [
  { key: 'system', label: 'System' },
  { key: 'light', label: 'Light' },
  { key: 'dark', label: 'Dark' },
];

function ThemePicker() {
  const [pref, setPref] = useState<ThemePreference>(() => getThemePreference());
  return (
    <div>
      <div className="segmented" role="group" aria-label="Theme">
        {THEME_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            type="button"
            className={`segmented__item${pref === opt.key ? ' segmented__item--active' : ''}`}
            onClick={() => {
              setPref(opt.key);
              applyThemePreference(opt.key);
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <p className="muted" style={{ margin: '0.6rem 0 0', fontSize: '0.85rem' }}>
        System follows your device's light or dark setting.
      </p>
    </div>
  );
}
