import { useEffect, useState, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  SearchX,
  Search,
  Shield,
  PauseCircle,
  PlayCircle,
  CreditCard,
} from 'lucide-react';
import { admin, type TenantAdmin } from '../services/api';

// ── Status/plan helpers ─────────────────────────────────────────

const statusBadge: Record<string, string> = {
  active: 'bg-green-50 text-green-700',
  suspended: 'bg-red-50 text-red-700',
  cancelled: 'bg-gray-50 text-gray-700',
  trial: 'bg-blue-50 text-blue-700',
};

const planBadge: Record<string, string> = {
  trial: 'bg-blue-50 text-blue-700',
  subscription: 'bg-purple-50 text-purple-700',
  cancelled: 'bg-gray-50 text-gray-700',
};

const statusLabels: Record<string, string> = {
  active: 'Activo',
  suspended: 'Suspendido',
  cancelled: 'Cancelado',
  trial: 'Prueba',
};

const planLabels: Record<string, string> = {
  trial: 'Prueba gratis',
  subscription: 'Suscripción',
  cancelled: 'Cancelado',
};

// ── Admin Page ──────────────────────────────────────────────────

export default function Admin() {
  const [data, setData] = useState<TenantAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [planFilter, setPlanFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // ── Fetch ──
  const fetchTenants = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: { status?: string; plan?: string } = {};
      if (statusFilter) params.status = statusFilter;
      if (planFilter) params.plan = planFilter;
      const result = await admin.tenants(params);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar tenants');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, planFilter]);

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  // ── Actions ──
  const handleSuspend = async (id: string, name: string) => {
    if (!window.confirm(`¿Suspendé a "${name}"? El tenant perderá acceso al sistema.`)) return;
    setActionLoading(id);
    try {
      await admin.suspend(id);
      fetchTenants();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al suspender');
    } finally {
      setActionLoading(null);
    }
  };

  const handleActivate = async (id: string, name: string) => {
    if (!window.confirm(`¿Activá a "${name}"? El tenant recuperará el acceso al sistema.`)) return;
    setActionLoading(id);
    try {
      await admin.activate(id);
      fetchTenants();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al activar');
    } finally {
      setActionLoading(null);
    }
  };

  const handleMarkPaid = async (id: string, name: string) => {
    if (!window.confirm(`¿Marcá a "${name}" como pagado? Se activará como suscripción activa.`)) return;
    setActionLoading(id);
    try {
      await admin.markPaid(id);
      fetchTenants();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al marcar como pagado');
    } finally {
      setActionLoading(null);
    }
  };

  // ── Filter by search ──
  const filtered = data.filter((t) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      t.name.toLowerCase().includes(q) ||
      t.email.toLowerCase().includes(q) ||
      t.slug.toLowerCase().includes(q)
    );
  });

  // ── Render ──
  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <Shield size={24} className="text-clinic-500" />
          <div>
            <h1 className="text-xl font-bold text-gray-900">Administración</h1>
            <p className="mt-1 text-sm text-gray-500">Gestión global de tenants</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Buscar por nombre, email o slug..."
            className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
          />
        </div>

        {/* Status filter */}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
        >
          <option value="">Todos los estados</option>
          <option value="active">Activo</option>
          <option value="suspended">Suspendido</option>
          <option value="cancelled">Cancelado</option>
        </select>

        {/* Plan filter */}
        <select
          value={planFilter}
          onChange={(e) => setPlanFilter(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
        >
          <option value="">Todos los planes</option>
          <option value="trial">Prueba</option>
          <option value="subscription">Suscripción</option>
          <option value="cancelled">Cancelado</option>
        </select>

        <button
          onClick={fetchTenants}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          {loading && <Loader2 size={16} className="animate-spin" />}
          Actualizar
        </button>
      </div>

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
            onClick={fetchTenants}
            className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX size={40} className="text-gray-300" />
          <p className="mt-4 text-sm text-gray-500">
            {data.length === 0 ? 'No hay tenants registrados' : 'No se encontraron resultados'}
          </p>
        </div>
      )}

      {/* Table */}
      {!loading && !error && filtered.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Tenant</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Plan</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Estado</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Prueba vence</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Creado</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((tenant) => (
                <tr key={tenant.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <div>
                      <p className="font-medium text-gray-900">{tenant.name}</p>
                      <p className="text-xs text-gray-500">{tenant.email}</p>
                      <p className="text-xs text-gray-400">/{tenant.slug}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        planBadge[tenant.plan] || 'bg-gray-50 text-gray-600'
                      }`}
                    >
                      {planLabels[tenant.plan] || tenant.plan}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        statusBadge[tenant.status] || 'bg-gray-50 text-gray-600'
                      }`}
                    >
                      {statusLabels[tenant.status] || tenant.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {tenant.trial_ends_at
                      ? new Date(tenant.trial_ends_at).toLocaleDateString('es-AR', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })
                      : '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {new Date(tenant.created_at).toLocaleDateString('es-AR', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {/* Suspend */}
                      {tenant.status !== 'suspended' && (
                        <button
                          onClick={() => handleSuspend(tenant.id, tenant.name)}
                          disabled={actionLoading === tenant.id}
                          className="rounded-lg p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 transition-colors disabled:opacity-50"
                          title="Suspender"
                        >
                          {actionLoading === tenant.id ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <PauseCircle size={16} />
                          )}
                        </button>
                      )}

                      {/* Activate */}
                      {tenant.status === 'suspended' && (
                        <button
                          onClick={() => handleActivate(tenant.id, tenant.name)}
                          disabled={actionLoading === tenant.id}
                          className="rounded-lg p-1.5 text-gray-400 hover:bg-green-50 hover:text-green-600 transition-colors disabled:opacity-50"
                          title="Activar"
                        >
                          {actionLoading === tenant.id ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <PlayCircle size={16} />
                          )}
                        </button>
                      )}

                      {/* Mark as paid */}
                      {tenant.plan === 'trial' && tenant.status !== 'suspended' && (
                        <button
                          onClick={() => handleMarkPaid(tenant.id, tenant.name)}
                          disabled={actionLoading === tenant.id}
                          className="rounded-lg p-1.5 text-gray-400 hover:bg-purple-50 hover:text-purple-600 transition-colors disabled:opacity-50"
                          title="Marcar como pagado"
                        >
                          {actionLoading === tenant.id ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <CreditCard size={16} />
                          )}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
