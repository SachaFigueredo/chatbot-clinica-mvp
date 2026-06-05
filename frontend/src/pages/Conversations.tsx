import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare,
  Filter,
  Loader2,
  AlertCircle,
  SearchX,
  Phone,
  Globe,
  User,
  Bot,
  ChevronRight,
} from 'lucide-react';
import { format, parseISO, formatDistanceToNow } from 'date-fns';
import { es } from 'date-fns/locale';
import { conversations, type Conversation, type ConversationStatus } from '../services/api';

// ── Helpers ────────────────────────────────────────────────────

const statusLabels: Record<ConversationStatus, string> = {
  active: 'Activa',
  escalated: 'Derivada',
  resolved: 'Resuelta',
  archived: 'Archivada',
};

const statusColors: Record<ConversationStatus, string> = {
  active: 'bg-green-100 text-green-700',
  escalated: 'bg-red-100 text-red-700',
  resolved: 'bg-gray-100 text-gray-600',
  archived: 'bg-transparent text-gray-400 border border-gray-200',
};

const channelIcons: Record<string, React.ReactNode> = {
  whatsapp: <Phone size={14} />,
  web: <Globe size={14} />,
};

const channelLabels: Record<string, string> = {
  whatsapp: 'WhatsApp',
  web: 'Web',
};

const statusFilterOptions = [
  { label: 'Todas', value: '' },
  { label: 'Activas', value: 'active' },
  { label: 'Derivadas', value: 'escalated' },
  { label: 'Resueltas', value: 'resolved' },
  { label: 'Archivadas', value: 'archived' },
];

const channelFilterOptions = [
  { label: 'Todos', value: '' },
  { label: 'WhatsApp', value: 'whatsapp' },
  { label: 'Web', value: 'web' },
];

function formatRelativeTime(iso: string | null): string {
  if (!iso) return '';
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true, locale: es });
  } catch {
    return '';
  }
}

function truncate(text: string | null, max: number): string {
  if (!text) return 'Sin mensajes';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

function getSenderLabel(origin: string): string {
  switch (origin) {
    case 'patient':
      return 'Paciente';
    case 'bot':
      return 'Bot';
    case 'human':
      return 'Recepcionista';
    default:
      return origin;
  }
}

// ── Conversations Page ─────────────────────────────────────────

export default function Conversations() {
  const navigate = useNavigate();
  const [data, setData] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [escalatedCount, setEscalatedCount] = useState(0);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Filters
  const [filterStatus, setFilterStatus] = useState('');
  const [filterChannel, setFilterChannel] = useState('');

  // ── Fetch ──
  const fetchConversations = useCallback(async () => {
    try {
      const result = await conversations.list({
        status: filterStatus || undefined,
        channel: filterChannel || undefined,
      });
      setData(result);
      setError(null);
    } catch (err) {
      if (!loading) {
        setError(err instanceof Error ? err.message : 'Error al cargar conversaciones');
      }
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterChannel, loading]);

  // Initial fetch
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Polling for escalated count
  useEffect(() => {
    const checkEscalated = async () => {
      try {
        const result = await conversations.list({ status: 'escalated' });
        setEscalatedCount(result.length);
      } catch {
        // silent
      }
    };

    checkEscalated();
    pollingRef.current = setInterval(checkEscalated, 15000);

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  // ── Render ──
  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Conversaciones</h1>
          <p className="mt-1 text-sm text-gray-500">
            Gestioná las conversaciones con pacientes
            {escalatedCount > 0 && (
              <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-600">
                <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
                {escalatedCount} derivada{escalatedCount !== 1 ? 's' : ''}
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <Filter size={18} className="text-gray-400" />
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
          >
            {statusFilterOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filterChannel}
            onChange={(e) => setFilterChannel(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
          >
            {channelFilterOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={32} className="animate-spin text-clinic-500" />
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <AlertCircle size={40} className="text-red-400" />
          <p className="mt-4 text-sm text-gray-600">{error}</p>
          <button
            onClick={fetchConversations}
            className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && data.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <MessageSquare size={40} className="text-gray-300" />
          <p className="mt-4 text-sm text-gray-500">No hay conversaciones</p>
        </div>
      )}

      {/* List */}
      {!loading && !error && data.length > 0 && (
        <div className="space-y-3">
          {data.map((conv) => (
            <button
              key={conv.id}
              onClick={() => navigate(`/conversations/${conv.id}`)}
              className="w-full rounded-xl border bg-white p-4 text-left shadow-sm transition-all hover:shadow-md hover:border-gray-200"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Header row */}
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-gray-900 truncate">
                      {conv.patient.name || conv.patient.phone_number}
                    </span>
                    <span className="text-xs text-gray-400">{conv.patient.phone_number}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[conv.status]}`}
                    >
                      {statusLabels[conv.status]}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                      {channelIcons[conv.channel]}
                      {channelLabels[conv.channel]}
                    </span>
                  </div>

                  {/* Last message preview */}
                  <p className="text-sm text-gray-500 truncate">
                    <span className="text-xs text-gray-400 mr-1">
                      {conv.last_message
                        ? `${getSenderLabel('')}:`
                        : ''}
                    </span>
                    {truncate(conv.last_message, 80)}
                  </p>
                </div>

                {/* Right side */}
                <div className="flex flex-col items-end gap-2 flex-shrink-0">
                  <span className="text-xs text-gray-400 whitespace-nowrap">
                    {formatRelativeTime(conv.last_message_at || conv.updated_at)}
                  </span>
                  <ChevronRight size={16} className="text-gray-300" />
                </div>
              </div>

              {/* Escalated to */}
              {conv.status === 'escalated' && conv.escalated_to && (
                <div className="mt-2 flex items-center gap-1.5 text-xs text-red-500">
                  <User size={12} />
                  En manos de <span className="font-medium">{conv.escalated_to.name}</span>
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
