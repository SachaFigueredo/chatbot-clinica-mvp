import { useEffect, useState, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  CreditCard,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
} from 'lucide-react';
import { billing, type BillingStatus } from '../services/api';
import { formatDistanceToNow, differenceInDays } from 'date-fns';
import { es } from 'date-fns/locale';

// ── Props ──────────────────────────────────────────────────────

interface Props {
  onNotification: (n: { type: 'success' | 'error'; message: string }) => void;
}

// ── Status helpers ──────────────────────────────────────────────

const planLabels: Record<string, string> = {
  trial: 'Prueba gratuita',
  subscription: 'Suscripción',
  cancelled: 'Cancelada',
};

const statusColors: Record<string, string> = {
  active: 'bg-green-50 text-green-700 border-green-200',
  suspended: 'bg-red-50 text-red-700 border-red-200',
  cancelled: 'bg-gray-50 text-gray-700 border-gray-200',
};

const statusLabels: Record<string, string> = {
  active: 'Activo',
  suspended: 'Suspendido',
  cancelled: 'Cancelado',
};

// ── Billing Page ────────────────────────────────────────────────

export default function BillingSettings({ onNotification }: Props) {
  const [data, setData] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Actions
  const [subscribing, setSubscribing] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  // ── Fetch ──
  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await billing.status();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar estado de facturación');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // ── Subscribe ──
  const handleSubscribe = async () => {
    setSubscribing(true);
    try {
      const res = await billing.checkout();
      // Redirect to Mercado Pago checkout
      window.location.href = res.init_point;
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al iniciar suscripción',
      });
    } finally {
      setSubscribing(false);
    }
  };

  // ── Cancel ──
  const handleCancel = async () => {
    if (!window.confirm('¿Estás seguro de cancelar la suscripción? Perderás acceso a las funciones premium al final del período.')) return;

    setCancelling(true);
    try {
      await billing.cancel();
      onNotification({ type: 'success', message: 'Suscripción cancelada' });
      fetchStatus();
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al cancelar suscripción',
      });
    } finally {
      setCancelling(false);
    }
  };

  // ── Trial formatting ──
  const trialInfo = (() => {
    if (!data?.trial_ends_at) return null;
    const end = new Date(data.trial_ends_at);
    const daysLeft = differenceInDays(end, new Date());
    const relative = formatDistanceToNow(end, { locale: es, addSuffix: true });

    if (daysLeft < 0) {
      return { label: 'Periodo de prueba vencido', daysLeft: 0, relative, expired: true };
    }
    return {
      label: daysLeft === 0 ? 'Último día de prueba' : `Quedan ${daysLeft} días de prueba`,
      daysLeft,
      relative,
      expired: false,
    };
  })();

  // ── Render ──
  return (
    <div>
      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={28} className="animate-spin text-clinic-500" />
        </div>
      )}

      {/* Error */}
      {error && !loading && (
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
      )}

      {/* Content */}
      {!loading && !error && data && (
        <div className="space-y-6">
          {/* Plan card */}
          <div className="rounded-xl border bg-white p-6 shadow-sm">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Plan actual</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {planLabels[data.plan] || data.plan}
                </p>
              </div>
              <div
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  statusColors[data.status] || 'bg-gray-50 text-gray-600'
                }`}
              >
                {statusLabels[data.status] || data.status}
              </div>
            </div>

            {/* Trial info */}
            {data.plan === 'trial' && trialInfo && (
              <div
                className={`mt-4 flex items-center gap-2 rounded-lg border px-4 py-3 text-sm ${
                  trialInfo.expired
                    ? 'border-red-200 bg-red-50 text-red-700'
                    : trialInfo.daysLeft <= 3
                      ? 'border-amber-200 bg-amber-50 text-amber-700'
                      : 'border-blue-200 bg-blue-50 text-blue-700'
                }`}
              >
                {trialInfo.expired ? (
                  <AlertTriangle size={18} />
                ) : (
                  <Clock size={18} />
                )}
                <span className="font-medium">{trialInfo.label}</span>
                <span className="opacity-70">({trialInfo.relative})</span>
              </div>
            )}

            {/* Days remaining for cancelled */}
            {data.plan === 'cancelled' && data.days_remaining != null && data.days_remaining > 0 && (
              <div className="mt-4 flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700">
                <Clock size={18} />
                <span>
                  Acceso activo por {data.days_remaining} día{data.days_remaining !== 1 ? 's' : ''} más
                </span>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="rounded-xl border bg-white p-6 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900">Acciones</h3>
            <p className="mt-1 text-sm text-gray-500">
              {data.plan === 'trial'
                ? 'Suscribite para seguir usando todas las funciones cuando termine el periodo de prueba.'
                : data.plan === 'cancelled'
                  ? 'Tu suscripción está cancelada. Reactivala para seguir usando el servicio.'
                  : 'Gestioná tu suscripción activa.'}
            </p>

            <div className="mt-4 flex flex-wrap gap-3">
              {/* Subscribe / Reactivate */}
              {(data.plan === 'trial' || data.plan === 'cancelled') && (
                <button
                  onClick={handleSubscribe}
                  disabled={subscribing}
                  className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
                >
                  {subscribing && <Loader2 size={16} className="animate-spin" />}
                  <CreditCard size={16} />
                  {data.plan === 'cancelled' ? 'Reactivar suscripción' : 'Suscribirse'}
                </button>
              )}

              {/* Cancel */}
              {data.plan === 'subscription' && data.status !== 'cancelled' && (
                <button
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="inline-flex items-center gap-2 rounded-lg border border-red-200 px-5 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                >
                  {cancelling && <Loader2 size={16} className="animate-spin" />}
                  <XCircle size={16} />
                  Cancelar suscripción
                </button>
              )}

              {/* Refresh */}
              <button
                onClick={fetchStatus}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                Actualizar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
