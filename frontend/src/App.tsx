import { NavLink, Route, Routes } from 'react-router-dom';
import { Dashboard } from '@/components/Dashboard';
import { HealthGate } from '@/components/HealthGate';
import { ReviewQueue } from '@/components/ReviewQueue';
import { Upload } from '@/components/Upload';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `app-nav__link${isActive ? ' app-nav__link--active' : ''}`;

function App() {
  return (
    <HealthGate>
      <div className="app-shell">
        <nav className="app-nav">
          <NavLink to="/" className="app-nav__brand">Invoxa</NavLink>
          <NavLink to="/" end className={navLinkClass}>Dashboard</NavLink>
          <NavLink to="/upload" className={navLinkClass}>Upload</NavLink>
          <NavLink to="/review" className={navLinkClass}>Review queue</NavLink>
        </nav>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/review" element={<ReviewQueue />} />
          </Routes>
        </main>
      </div>
    </HealthGate>
  );
}

export default App;
