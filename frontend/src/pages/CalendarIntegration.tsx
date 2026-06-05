import { useEffect, useState, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  Calendar,
  CheckCircle,
  XCircle,
  ExternalLink,
  Unlink,
} from 'lucide-react';
import { calendar, type CalendarStatus } from '../services/api';

// ── Props ──────────────────────────────────────────────────────

interface Props {
  onNotification: (n: { type: 'success' | 'error'; message: string }) => void;
}

// ── Confirm Dialog ─────────────────────────────────────────────

function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  loading,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        <p className="mt-2 text-sm text-gray-600">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 transition-colors disabled:opacity-50"
          >
            {loading && <Loader2 size={16} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── CalendarIntegration Page ───────────────────────────────────

export default function CalendarIntegrationPage({ onNotification }: Props) {
  const [status, setStatus] = useState<CalendarStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Connect flow
  const [connecting, setConnecting] = useState(false);

  // Disconnect
  const [showDisconnect, setShowDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  // ── Fetch status ──
  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await calendar.status();
      setStatus(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al verificar estado del calendario');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // ── Connect ──
  const handleConnect = async () => {
    setConnecting(true);
    try {
      const { url } = await calendar.getAuthUrl();
      // Redirect browser to Google OAuth
      window.location.href = url;
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al iniciar conexión con Google Calendar',
      });
      setConnecting(false);
    }
  };

  // ── Disconnect ──
  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await calendar.disconnect();
      onNotification({ type: 'success', message: 'Google Calendar desconectado correctamente' });
      setShowDisconnect(false);
      // Refresh status
      const result = await calendar.status();
      setStatus(result);
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al desconectar Google Calendar',
      });
    } finally {
      setDisconnecting(false);
    }
  };

  // ── Loading ──
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={28} className="animate-spin text-clinic-500" />
      </div>
    );
  }

  // ── Error ──
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <AlertCircle size={40} className="text-red-400" />
        <p className="mt-4 text-sm text-gray-600">{error}</p>
        <button
          onClick={fetchStatus}
          className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
        >
          Reintentar
        </button>
      </div>
    );
  }

  // ── Render ──
  return (
    <div className="max-w-xl">
      <p className="mb-6 text-sm text-gray-500">
        Conectá Google Calendar para que el bot pueda consultar disponibilidad, crear y gestionar
        turnos automáticamente.
      </p>

      {status?.connected ? (
        /* ── Connected state ── */
        <div className="rounded-xl border border-green-200 bg-green-50 p-6">
          <div className="flex items-start gap-4">
            <div className="rounded-full bg-green-100 p-3">
              <Calendar size={28} className="text-green-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-700">
                  <CheckCircle size={14} />
                  Conectado
                </span>
              </div>
              {status.email && (
                <p className="mt-3 text-sm text-gray-600">
                  <span className="font-medium text-gray-900">Cuenta:</span> {status.email}
                </p>
              )}
              {status.calendar_name && (
                <p className="mt-1 text-sm text-gray-600">
                  <span className="font-medium text-gray-900">Calendario:</span> {status.calendar_name}
                </p>
              )}
              <p className="mt-1 text-xs text-green-600">
                El bot puede leer y escribir eventos en este calendario.
              </p>

              <div className="mt-6">
                <button
                  onClick={() => setShowDisconnect(true)}
                  className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
                >
                  <Unlink size={16} />
                  Desconectar
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* ── Disconnected state ── */
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-6">
          <div className="flex items-start gap-4">
            <div className="rounded-full bg-gray-100 p-3">
              <Calendar size={28} className="text-gray-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold text-gray-900">Google Calendar</h3>
              <p className="mt-1 text-sm text-gray-500">
                Conectá tu calendario para que el bot pueda gestionar turnos automáticamente.
              </p>
              <button
                onClick={handleConnect}
                disabled={connecting}
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
              >
                {connecting ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <ExternalLink size={16} />
                )}
                Conectar Google Calendar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Disconnect confirm */}
      <ConfirmDialog
        open={showDisconnect}
        title="Desconectar Google Calendar"
        message="Al desconectar, el bot no podrá crear ni modificar turnos en el calendario. ¿Estás seguro?"
        confirmLabel="Desconectar"
        onConfirm={handleDisconnect}
        onCancel={() => setShowDisconnect(false)}
        loading={disconnecting}
      />
    </div>
  );
}
