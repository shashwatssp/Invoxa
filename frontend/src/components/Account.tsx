import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { applyThemePreference, getThemePreference, type ThemePreference } from '@/lib/theme';
import { exportAccountData, fetchDigest, friendlyError } from '@/lib/api';

/** Profile + session: the one place that always offers Sign out,
 * including on phones where the top nav is hidden. */
export function Account() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [digestEmail, setDigestEmail] = useState('');
  const [preparingDigest, setPreparingDigest] = useState(false);
  const [digestError, setDigestError] = useState<string | null>(null);

  /** Download the whole account (profile, invoices, folders, review queue) as JSON. */
  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await exportAccountData();
    } catch (err) {
      setExportError(friendlyError(err, 'Could not export your data.'));
    } finally {
      setExporting(false);
    }
  };

  /** Open the user's email app (Gmail, etc.) with the digest prefilled —
   * sending stays manual, and no SMTP config exists anywhere. */
  const handleOpenDigest = async () => {
    const recipient = digestEmail.trim();
    if (!recipient || preparingDigest) return;
    setPreparingDigest(true);
    setDigestError(null);
    try {
      const digest = await fetchDigest(7);
      const body = digest.summary_lines.join('\n') +
        (digest.narrative ? `\n\n${digest.narrative}` : '');
      const subject = `Invoxa digest — the last ${digest.window_days} days`;
      window.location.href = `mailto:${recipient}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    } catch (err) {
      setDigestError(friendlyError(err, 'Could not prepare the digest. Please try again.'));
    } finally {
      setPreparingDigest(false);
    }
  };

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
          <h2>Weekly digest email</h2>
        </div>
        <p className="muted" style={{ margin: '0 0 1rem', fontSize: '0.9rem' }}>
          Put in an email address and your email app opens with the
          plain-English weekly summary already written — what was processed,
          what needs review, and what is due soon. You press send. No setup.
        </p>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            type="email"
            value={digestEmail}
            onChange={(e) => setDigestEmail(e.target.value)}
            placeholder={user?.email ?? 'you@example.com'}
            aria-label="Email address for the digest"
            style={{ flex: '1 1 220px' }}
          />
          <button
            type="button"
            className="button button--secondary"
            onClick={() => void handleOpenDigest()}
            disabled={preparingDigest || !digestEmail.trim()}
          >
            {preparingDigest ? 'Preparing…' : 'Open email app'}
          </button>
        </div>
        {digestError && <div className="error-banner" style={{ marginTop: '0.75rem' }}>{digestError}</div>}
      </section>

      <section className="card">
        <div className="card__header">
          <h2>Your data</h2>
        </div>
        <p className="muted" style={{ margin: '0 0 1rem', fontSize: '0.9rem' }}>
          Download everything in your account — profile, invoices, folders,
          and review history — as one JSON file.
        </p>
        {exportError && <div className="error-banner">{exportError}</div>}
        <button type="button" className="button button--secondary" onClick={() => void handleExport()} disabled={exporting}>
          {exporting ? 'Preparing…' : 'Export my data'}
        </button>
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
