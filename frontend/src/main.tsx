import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from '@/App';
import { initTheme } from '@/lib/theme';
import '@/index.css';

// Set <html data-theme> before the first paint (no flash of wrong theme).
initTheme();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

// PWA: register the service worker so the app is installable on phones.
// Dev mode skips it (vite serves unbundled; no SW churn while editing).
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // A failed registration must never break the app - it just means
      // no offline shell / install prompt.
    });
  });
}
