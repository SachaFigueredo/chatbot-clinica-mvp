import { useEffect, useState } from 'react';
import {
  Calendar,
  Clock,
  MessageSquare,
  AlertCircle,
  XCircle,
  Loader2,
} from 'lucide-react';
import { dashboard, type DashboardStats } from '../services/api';

// ── Stat Card ──────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  color: 'blue' | 'yellow' | 'green' | 'red' | 'gray';
  prefix?: string;
  suffix?: string;
}

const colorMap = {
  blue: {
    bg: 'bg-blue-50',
    text: 'text-blue-600',
    icon: 'text-blue-500',
    ring: 'ring-blue-200',
  },
  yellow: {
    bg: 'bg-yellow-50',
    text: 'text-yellow-600',
    icon: 'text-yellow-500',
    ring: 'ring-yellow-200',
  },
  green: {
    bg: 'bg-green-50',
    text: 'text-green-600',
    icon: 'text-green-500',
    ring: 'ring-green-200',
  },
  red: {
    bg: 'bg-red-50',
    text: 'text-red-600',
    icon: 'text-red-500',
    ring: 'ring-red-200',
  },
  gray: {
    bg: 'bg-gray-50',
    text: 'text-gray-600',
    icon: 'text-gray-400',
    ring: 'ring-gray-200',
  },
};

function StatCard({ label, value, icon, color, prefix, suffix }: StatCardProps) {
  const c = colorMap[color];

  return (
    <div className="rounded-xl border bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <p className={`mt-2 text-3xl font-bold ${c.text}`}>
            {prefix}{value}{suffix}
          </p>
        </div>
        <div className={`rounded-lg ${c.bg} p-3 ${c.icon} ring-1 ${c.ring}`}>
          {icon}
        </div>
      </div>
    </div>
  );
}

// ── Stats Grid ─────────────────────────────────────────────────

const cardConfig: { key: keyof DashboardStats; label: string; icon: React.ReactNode; color: StatCardProps['color']; suffix?: string }[] = [
  { key: 'appointments_today', label: 'Turnos hoy', icon: <Calendar size={24} />, color: 'blue' },
  { key: 'pending_confirmations', label: 'Pendientes', icon: <Clock size={24} />, color: 'yellow' },
  { key: 'active_conversations', label: 'Activas', icon: <MessageSquare size={24} />, color: 'green' },
  { key: 'escalated_conversations', label: 'Derivadas', icon: <AlertCircle size={24} />, color: 'red' },
  { key: 'no_show_rate', label: 'No-show', icon: <XCircle size={24} />, color: 'gray', suffix: '%' },
];

// ── Dashboard Page ─────────────────────────────────────────────

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchStats = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await dashboard.stats();
        if (!cancelled) setStats(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Error al cargar estadísticas');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchStats();

    // Poll every 30s
    const interval = setInterval(fetchStats, 30000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // ── Loading state ──
  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={32} className="animate-spin text-clinic-500" />
      </div>
    );
  }

  // ── Error state ──
  if (error && !stats) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <AlertCircle size={40} className="text-red-400" />
        <p className="mt-4 text-sm text-gray-600">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
        >
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Resumen de actividad de tu clínica
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {stats &&
          cardConfig.map((card) => (
            <StatCard
              key={card.key}
              label={card.label}
              value={
                card.key === 'no_show_rate'
                  ? (stats[card.key] * 100).toFixed(1)
                  : stats[card.key]
              }
              icon={card.icon}
              color={card.color}
              suffix={card.suffix}
            />
          ))}
      </div>

      {/* Latest Activity (placeholder) */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">
          Actividad reciente
        </h2>
        <div className="rounded-xl border bg-white p-8 text-center shadow-sm">
          <MessageSquare size={32} className="mx-auto text-gray-300" />
          <p className="mt-3 text-sm text-gray-500">
            La sección de actividad reciente estará disponible próximamente.
          </p>
        </div>
      </div>
    </div>
  );
}
