import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  clearToken,
  fetchMe,
  getToken,
  login as apiLogin,
  setUnauthorizedHandler,
  signup as apiSignup,
  storeToken,
  type AuthUser,
} from '@/lib/api';

type Status = 'loading' | 'authenticated' | 'anonymous';

interface AuthContextValue {
  status: Status;
  user: AuthUser | null;
  signup: (email: string, password: string, name: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const USER_KEY = 'invoxa_user';

export function AuthProvider({ children }: { children: ReactNode }) {
  // Initialize synchronously: visitors without a stored token render the
  // anonymous UI on the very first paint (no login/signup -> "Open app" flash).
  const [status, setStatus] = useState<Status>(() => (getToken() ? 'loading' : 'anonymous'));
  const [user, setUser] = useState<AuthUser | null>(null);

  const logout = useCallback(() => {
    clearToken();
    localStorage.removeItem(USER_KEY);
    setUser(null);
    setStatus('anonymous');
  }, []);

  // Global 401 handler: expired/invalid session -> log out silently.
  useEffect(() => {
    setUnauthorizedHandler(() => logout());
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Restore the session on first mount.
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setStatus('anonymous');
      return;
    }
    fetchMe()
      .then((me) => {
        setUser(me);
        localStorage.setItem(USER_KEY, JSON.stringify(me));
        setStatus('authenticated');
      })
      .catch(() => {
        clearToken();
        localStorage.removeItem(USER_KEY);
        setStatus('anonymous');
      });
  }, []);

  const signup = useCallback(
    async (email: string, password: string, name: string) => {
      const res = await apiSignup(email, password, name);
      storeToken(res.token);
      setUser(res.user);
      localStorage.setItem(USER_KEY, JSON.stringify(res.user));
      setStatus('authenticated');
    },
    [],
  );

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiLogin(email, password);
    storeToken(res.token);
    setUser(res.user);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    setStatus('authenticated');
  }, []);

  const value = useMemo(
    () => ({ status, user, signup, login, logout }),
    [status, user, signup, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
