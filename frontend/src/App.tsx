import { NavLink, Route, Routes, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from '@/auth/AuthContext';
import { Dashboard } from '@/components/Dashboard';
import { HealthGate } from '@/components/HealthGate';
import { InvoiceDetail } from '@/components/InvoiceDetail';
import { Landing } from '@/components/Landing';
import { Login } from '@/components/Login';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { ReviewQueue } from '@/components/ReviewQueue';
import { Signup } from '@/components/Signup';
import { Upload } from '@/components/Upload';

const NAV_ITEMS = [
  { to: '/app', label: 'Dashboard', icon: IconHome, end: true },
  { to: '/app/upload', label: 'Upload', icon: IconUpload, end: false },
  { to: '/app/review', label: 'Review', icon: IconCheck, end: false },
];

function IconHome() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
    </svg>
  );
}

function IconUpload() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M9 11 12 14 20 6" />
      <path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9" />
    </svg>
  );
}

/** Shell for everything behind login. */
function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleSignOut = () => {
    logout();
    navigate('/', { replace: true });
  };

  const initial = (user?.name || user?.email || '?').trim().charAt(0).toUpperCase();

  return (
    <div className="app-shell">
      <nav className="app-nav">
        <NavLink to="/app" className="app-nav__brand">
          <span className="app-nav__brand-mark" aria-hidden>i</span>
          Invoxa
        </NavLink>
        <div className="app-nav__links">
          {NAV_ITEMS.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `app-nav__link${isActive ? ' app-nav__link--active' : ''}`}>
              {label}
            </NavLink>
          ))}
        </div>
        <div className="app-nav__user">
          <span className="avatar" aria-hidden>{initial}</span>
          <span className="app-nav__user-name" title={user?.email ?? ''}>
            {user?.name || user?.email}
          </span>
          <button type="button" className="button button--secondary" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </nav>
      <main className="app-main">
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="upload" element={<Upload />} />
          <Route path="review" element={<ReviewQueue />} />
          <Route path="invoices/:invoiceId" element={<InvoiceDetail />} />
          <Route path="*" element={<Dashboard />} />
        </Routes>
      </main>
      <nav className="app-tabbar" aria-label="Primary">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `app-tabbar__item${isActive ? ' app-tabbar__item--active' : ''}`}
          >
            <Icon />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public pages */}
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />

        {/* Protected app (behind the backend health gate) */}
        <Route
          path="/app/*"
          element={
            <ProtectedRoute>
              <HealthGate>
                <AppShell />
              </HealthGate>
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthProvider>
  );
}

export default App;
