export type ThemePreference = 'system' | 'light' | 'dark';

const KEY = 'invoxa_theme';

export function getThemePreference(): ThemePreference {
  const stored = localStorage.getItem(KEY);
  return stored === 'light' || stored === 'dark' ? stored : 'system';
}

function resolve(pref: ThemePreference): 'light' | 'dark' {
  if (pref !== 'system') return pref;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Apply the preference to <html data-theme> and persist it. */
export function applyThemePreference(pref: ThemePreference): void {
  document.documentElement.dataset.theme = resolve(pref);
  localStorage.setItem(KEY, pref);
}

/** Call once at startup: applies the stored theme before first paint
 * and keeps following the OS preference while on "System". */
export function initTheme(): void {
  applyThemePreference(getThemePreference());
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', () => {
      if (getThemePreference() === 'system') applyThemePreference('system');
    });
}
