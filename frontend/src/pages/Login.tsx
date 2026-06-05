import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Stethoscope, Mail, Lock, Loader2, Send } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { auth, onboarding } from '../services/api';

export default function Login() {
  const { user, token, login, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Magic link
  const [magicEmail, setMagicEmail] = useState('');
  const [magicSent, setMagicSent] = useState(false);
  const [magicSubmitting, setMagicSubmitting] = useState(false);
  const [showMagic, setShowMagic] = useState(false);

  // Already logged in — will redirect based on onboarding in App routing
  if (token && user && !authLoading) {
    // We redirect to dashboard; the Onboarding component will redirect
    // to /onboarding if needed. This avoids a second API call here.
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email, password });
      // Check onboarding — redirect incomplete users to /onboarding
      const onboardingStatus = await onboarding.status();
      navigate(onboardingStatus.completed ? '/dashboard' : '/onboarding');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al iniciar sesión');
    } finally {
      setSubmitting(false);
    }
  };

  const handleMagicLink = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMagicSubmitting(true);
    try {
      await auth.sendMagicLink(magicEmail);
      setMagicSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al enviar magic link');
    } finally {
      setMagicSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-clinic-50 to-blue-100 px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-clinic-500 shadow-lg shadow-clinic-200">
            <Stethoscope className="text-white" size={28} />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Panel Clínica</h1>
          <p className="mt-1 text-sm text-gray-500">
            Ingresá a tu panel de gestión
          </p>
        </div>

        {/* Card */}
        <div className="rounded-xl bg-white p-8 shadow-sm border">
          {showMagic ? (
            // ── Magic Link Form ──
            <>
              <h2 className="mb-1 text-lg font-semibold text-gray-900">
                Magic Link
              </h2>
              <p className="mb-6 text-sm text-gray-500">
                Ingresá tu email y te enviamos un enlace mágico para iniciar sesión.
              </p>

              {magicSent ? (
                <div className="rounded-lg bg-green-50 p-4 text-sm text-green-700">
                  <p className="font-medium">¡Email enviado!</p>
                  <p className="mt-1">
                    Revisá tu casilla de correo. El enlace expira en 15 minutos.
                  </p>
                </div>
              ) : (
                <form onSubmit={handleMagicLink} className="space-y-4">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">
                      Email
                    </label>
                    <div className="relative">
                      <Mail
                        size={18}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                      />
                      <input
                        type="email"
                        required
                        value={magicEmail}
                        onChange={(e) => setMagicEmail(e.target.value)}
                        placeholder="tu@email.com"
                        className="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-4 text-sm focus:border-clinic-500 focus:outline-none focus:ring-2 focus:ring-clinic-200"
                      />
                    </div>
                  </div>

                  {error && (
                    <p className="text-sm text-red-600">{error}</p>
                  )}

                  <button
                    type="submit"
                    disabled={magicSubmitting}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-clinic-500 py-2.5 text-sm font-semibold text-white hover:bg-clinic-600 disabled:opacity-60 transition-colors"
                  >
                    {magicSubmitting ? (
                      <Loader2 size={18} className="animate-spin" />
                    ) : (
                      <Send size={18} />
                    )}
                    Enviar Magic Link
                  </button>
                </form>
              )}

              <button
                onClick={() => {
                  setShowMagic(false);
                  setError(null);
                  setMagicSent(false);
                }}
                className="mt-4 text-sm text-clinic-600 hover:text-clinic-700"
              >
                ← Volver al inicio de sesión
              </button>
            </>
          ) : (
            // ── Login Form ──
            <>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">
                    Email
                  </label>
                  <div className="relative">
                    <Mail
                      size={18}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                    />
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="tu@email.com"
                      className="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-4 text-sm focus:border-clinic-500 focus:outline-none focus:ring-2 focus:ring-clinic-200"
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">
                    Contraseña
                  </label>
                  <div className="relative">
                    <Lock
                      size={18}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                    />
                    <input
                      type="password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-4 text-sm focus:border-clinic-500 focus:outline-none focus:ring-2 focus:ring-clinic-200"
                    />
                  </div>
                </div>

                {error && (
                  <p className="text-sm text-red-600">{error}</p>
                )}

                <button
                  type="submit"
                  disabled={submitting}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-clinic-500 py-2.5 text-sm font-semibold text-white hover:bg-clinic-600 disabled:opacity-60 transition-colors"
                >
                  {submitting ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <Lock size={18} />
                  )}
                  Ingresar
                </button>
              </form>

              <div className="mt-6 space-y-3">
                <button
                  onClick={() => {
                    setShowMagic(true);
                    setError(null);
                  }}
                  className="w-full text-center text-sm text-clinic-600 hover:text-clinic-700"
                >
                  ¿Olvidaste tu contraseña? Usá Magic Link
                </button>

                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-white px-2 text-gray-500">o</span>
                  </div>
                </div>

                <p className="text-center text-sm text-gray-500">
                  ¿No tenés cuenta?{' '}
                  <Link
                    to="/register"
                    className="font-medium text-clinic-600 hover:text-clinic-700"
                  >
                    Registrate
                  </Link>
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
