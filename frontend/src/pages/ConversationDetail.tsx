import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Loader2,
  AlertCircle,
  ArrowLeft,
  Send,
  User,
  Bot,
  Shield,
  ArrowLeftRight,
  Phone,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { useAuth } from '../contexts/AuthContext';
import {
  conversations,
  type ConversationDetail as ConvDetail,
  type ConversationMessage,
  type ConversationStatus,
} from '../services/api';

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

function formatTime(iso: string) {
  try {
    const d = parseISO(iso);
    return format(d, 'HH:mm', { locale: es });
  } catch {
    return '';
  }
}

function formatDateFull(iso: string) {
  try {
    const d = parseISO(iso);
    return format(d, "d 'de' MMM '·' HH:mm", { locale: es });
  } catch {
    return '';
  }
}

function getMessageStyle(origin: string) {
  switch (origin) {
    case 'patient':
      return 'self-start bg-gray-100 text-gray-900 rounded-bl-none';
    case 'bot':
      return 'self-end bg-blue-500 text-white rounded-br-none';
    case 'human':
      return 'self-end bg-clinic-500 text-white rounded-br-none';
    default:
      return 'self-start bg-gray-100 text-gray-900';
  }
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

function getSenderIcon(origin: string): React.ReactNode {
  switch (origin) {
    case 'patient':
      return <User size={14} />;
    case 'bot':
      return <Bot size={14} />;
    case 'human':
      return <Shield size={14} />;
    default:
      return null;
  }
}

// ── Conversation Detail Page ───────────────────────────────────

export default function ConversationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [conv, setConv] = useState<ConvDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [taking, setTaking] = useState(false);
  const [returning, setReturning] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── Fetch ──
  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    conversations
      .get(id)
      .then(setConv)
      .catch((err) => setError(err instanceof Error ? err.message : 'Conversación no encontrada'))
      .finally(() => setLoading(false));
  }, [id]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conv?.messages]);

  // ── Take conversation ──
  const handleTake = async () => {
    if (!id) return;
    setTaking(true);
    try {
      const updated = await conversations.take(id);
      setConv(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Error al tomar la conversación');
    } finally {
      setTaking(false);
    }
  };

  // ── Reply ──
  const handleReply = async () => {
    if (!id || !replyText.trim()) return;
    setSending(true);
    try {
      await conversations.reply(id, replyText.trim());
      setReplyText('');
      // Refetch to get updated messages
      const updated = await conversations.get(id);
      setConv(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Error al enviar mensaje');
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleReply();
    }
  };

  // ── Return to bot ──
  const handleReturnToBot = async () => {
    if (!id) return;
    setReturning(true);
    try {
      const updated = await conversations.returnToBot(id);
      setConv(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Error al devolver al bot');
    } finally {
      setReturning(false);
    }
  };

  // ── Loading ──
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={32} className="animate-spin text-clinic-500" />
      </div>
    );
  }

  // ── Error ──
  if (error || !conv) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <AlertCircle size={40} className="text-red-400" />
        <p className="mt-4 text-sm text-gray-600">{error || 'Conversación no encontrada'}</p>
        <button
          onClick={() => navigate('/conversations')}
          className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
        >
          Volver a conversaciones
        </button>
      </div>
    );
  }

  // ── Compute action state ──
  const isEscalated = conv.status === 'escalated';
  const takenByMe = isEscalated && conv.escalated_to?.id === user?.id;
  const takenByOther = isEscalated && conv.escalated_to && conv.escalated_to.id !== user?.id;
  const canTake = isEscalated && !conv.escalated_to;
  const canReply = takenByMe;
  const canReturnToBot = takenByMe;

  // ── Render ──
  return (
    <div className="flex h-full flex-col">
      {/* Back button + header */}
      <div className="mb-4">
        <button
          onClick={() => navigate('/conversations')}
          className="mb-3 inline-flex items-center gap-2 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
        >
          <ArrowLeft size={18} />
          Volver a conversaciones
        </button>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold text-gray-900">
              {conv.patient.name || conv.patient.phone_number}
            </h1>
            <div className="mt-1 flex items-center gap-2 text-sm text-gray-500">
              <Phone size={14} />
              {conv.patient.phone_number}
              <span
                className={`ml-1 rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[conv.status]}`}
              >
                {statusLabels[conv.status]}
              </span>
              <span className="text-xs text-gray-400">
                · {formatDateFull(conv.created_at)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Action bar */}
      <div className="mb-4 rounded-lg border bg-white p-3 shadow-sm">
        {conv.status === 'active' && (
          <div className="flex items-center gap-2 text-sm text-green-600">
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            Bot activo — el asistente está gestionando esta conversación
          </div>
        )}

        {canTake && (
          <button
            onClick={handleTake}
            disabled={taking}
            className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
          >
            {taking ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <ArrowLeftRight size={16} />
            )}
            Tomar conversación
          </button>
        )}

        {takenByOther && (
          <div className="flex items-center gap-2 text-sm text-red-500">
            <User size={16} />
            En manos de{' '}
            <span className="font-medium">{conv.escalated_to?.name}</span>
          </div>
        )}

        {canReturnToBot && (
          <div className="flex items-center gap-3">
            <button
              onClick={handleReturnToBot}
              disabled={returning}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              {returning ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Bot size={16} />
              )}
              Devolver al bot
            </button>
          </div>
        )}
      </div>

      {/* Chat window */}
      <div className="flex-1 overflow-hidden rounded-xl border bg-white shadow-sm">
        <div className="flex h-[400px] flex-col">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {conv.messages.length === 0 && (
              <div className="flex items-center justify-center h-full text-sm text-gray-400">
                No hay mensajes en esta conversación
              </div>
            )}

            {conv.messages.map((msg, idx) => {
              const isLast = idx === conv.messages.length - 1;
              const isSystem = msg.origin === 'bot' && (msg.content.includes('deriv') || msg.content.includes('control') || msg.content.includes('bot'));

              return (
                <div
                  key={msg.id}
                  className={`flex ${getMessageStyle(msg.origin)} max-w-[75%] rounded-xl px-4 py-2.5 ${
                    isLast ? 'mb-1' : ''
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="flex items-center gap-1 text-xs font-medium opacity-70">
                        {getSenderIcon(msg.origin)}
                        {getSenderLabel(msg.origin)}
                      </span>
                      <span className="text-xs opacity-50">
                        {formatTime(msg.created_at)}
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">
                      {msg.content}
                    </p>
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Reply input */}
          {canReply && (
            <div className="border-t bg-gray-50 p-3">
              <div className="flex items-end gap-2">
                <textarea
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Escribí tu respuesta..."
                  rows={2}
                  className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
                />
                <button
                  onClick={handleReply}
                  disabled={sending || !replyText.trim()}
                  className="inline-flex h-[42px] w-[42px] items-center justify-center rounded-lg bg-clinic-500 text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
                >
                  {sending ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <Send size={18} />
                  )}
                </button>
              </div>
              <p className="mt-1 text-xs text-gray-400">
                Enter para enviar · Shift+Enter para nueva línea
              </p>
            </div>
          )}

          {/* Not taking notice */}
          {isEscalated && !canTake && !takenByMe && !takenByOther && !conv.escalated_to && (
            <div className="border-t bg-gray-50 p-4 text-center text-sm text-gray-400">
              Tomá la conversación para poder responder
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
