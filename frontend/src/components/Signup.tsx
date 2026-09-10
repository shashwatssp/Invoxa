import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { friendlyError } from '@/lib/api';

export function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const passwordTooShort = password.length > 0 && password.length < 8;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim()) {
      setError('Enter your email to continue.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signup(email.trim(), password, name.trim());
      navigate('/app', { replace: true });
    } catch (err) {
      setError(friendlyError(err, 'Could not create your account. Please try again.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <Link to="/" className="app-nav__brand auth-brand">
        <span className="app-nav__brand-mark" aria-hidden>i</span>
        Invoxa
      </Link>
      <form className="card auth-card" onSubmit={handleSubmit} noValidate>
        <h1>Create your account</h1>
        <p className="muted">Free, takes under a minute.</p>

        {error && <div className="error-banner" role="alert">{error}</div>}

        <label className="field">
          <span className="field__label">Name <span className="muted">(optional)</span></span>
          <input
            className="input"
            type="text"
            autoComplete="name"
            placeholder="Your name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>

        <label className="field">
          <span className="field__label">Email</span>
          <input
            className="input"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>

        <label className="field">
          <span className="field__label">Password</span>
          <div className="password-wrap">
            <input
              className="input"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              placeholder="At least 8 characters"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={passwordTooShort}
              required
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
          {passwordTooShort && (
            <span className="field-hint" role="alert">At least 8 characters, please.</span>
          )}
        </label>

        <div className="info-banner auth-perks">
          Every account can upload receipts and review them. One login does it all.
        </div>

        <button className="button button--large auth-submit" type="submit" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>

        <p className="muted auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </div>
  );
}
