import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import {
  auth,
  setToken,
  clearToken,
  getToken,
  type User,
  type LoginRequest,
  type RegisterRequest,
} from '../services/api';

// ── Types ──────────────────────────────────────────────────────

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  error: string | null;
  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

// ── Context ────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(getToken());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // On mount: validate stored token
  useEffect(() => {
    const stored = getToken();
    if (!stored) {
      setLoading(false);
      return;
    }

    auth
      .me()
      .then((u) => {
        setUser(u);
        setTokenState(stored);
      })
      .catch(() => {
        // Token is invalid — clean up
        clearToken();
        setTokenState(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (data: LoginRequest) => {
    setError(null);
    setLoading(true);
    try {
      const res = await auth.login(data);
      setToken(res.access_token);
      setTokenState(res.access_token);

      // Fetch full user info
      const u = await auth.me();
      setUser(u);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al iniciar sesión';
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (data: RegisterRequest) => {
    setError(null);
    setLoading(true);
    try {
      const res = await auth.register(data);
      setToken(res.access_token);
      setTokenState(res.access_token);

      const u = await auth.me();
      setUser(u);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al registrarse';
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    setUser(null);
    setError(null);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const u = await auth.me();
      setUser(u);
    } catch {
      logout();
    }
  }, [logout]);

  return (
    <AuthContext.Provider
      value={{ user, token, loading, error, login, register, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ───────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
