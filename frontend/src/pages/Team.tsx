import { useEffect, useState, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  SearchX,
  UserPlus,
  Trash2,
  X,
} from 'lucide-react';
import { team, type TeamMember, type InviteInput } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

// ── Props ──────────────────────────────────────────────────────

interface Props {
  onNotification: (n: { type: 'success' | 'error'; message: string }) => void;
}

// ── Role labels ────────────────────────────────────────────────

const roleLabels: Record<string, string> = {
  admin: 'Administrador',
  recepcionista: 'Recepcionista',
};

// ── Invite Modal ───────────────────────────────────────────────

function InviteModal({
  open,
  onClose,
  onInvite,
  saving,
}: {
  open: boolean;
  onClose: () => void;
  onInvite: (data: InviteInput) => void;
  saving: boolean;
}) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'admin' | 'recepcionista'>('recepcionista');

  useEffect(() => {
    if (open) {
      setEmail('');
      setRole('recepcionista');
    }
  }, [open]);

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    onInvite({ email: email.trim(), role });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Invitar miembro</h3>
          <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              placeholder="correo@ejemplo.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Rol</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as 'admin' | 'recepcionista')}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
            >
              <option value="recepcionista">Recepcionista</option>
              <option value="admin">Administrador</option>
            </select>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving || !email.trim()}
              className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
            >
              {saving && <Loader2 size={16} className="animate-spin" />}
              Invitar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
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
  danger,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  danger?: boolean;
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
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50 ${
              danger ? 'bg-red-500 hover:bg-red-600' : 'bg-clinic-500 hover:bg-clinic-600'
            }`}
          >
            {loading && <Loader2 size={16} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Team Page ──────────────────────────────────────────────────

export default function TeamPage({ onNotification }: Props) {
  const { user } = useAuth();
  const [data, setData] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Invite
  const [inviteOpen, setInviteOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  // Remove
  const [removeTarget, setRemoveTarget] = useState<TeamMember | null>(null);
  const [deleting, setDeleting] = useState(false);

  // ── Fetch ──
  const fetchMembers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await team.list();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar miembros del equipo');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMembers();
  }, [fetchMembers]);

  // ── Invite ──
  const handleInvite = async (input: InviteInput) => {
    setSaving(true);
    try {
      await team.invite(input);
      onNotification({ type: 'success', message: `Invitación enviada a ${input.email}` });
      setInviteOpen(false);
      fetchMembers();
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al invitar miembro',
      });
    } finally {
      setSaving(false);
    }
  };

  // ── Remove ──
  const handleRemove = async () => {
    if (!removeTarget) return;
    setDeleting(true);
    try {
      await team.remove(removeTarget.id);
      onNotification({ type: 'success', message: `${removeTarget.name} fue removido del equipo` });
      setRemoveTarget(null);
      fetchMembers();
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al remover miembro',
      });
    } finally {
      setDeleting(false);
    }
  };

  // ── Can remove? ──
  const canRemove = (member: TeamMember): boolean => {
    if (member.id === user?.id) return false; // cannot remove self
    if (member.role === 'admin') {
      // Check if there are other admins
      const otherAdmin = data.some((m) => m.role === 'admin' && m.id !== member.id && m.is_active);
      if (!otherAdmin) return false; // cannot remove last admin
    }
    return true;
  };

  const removeError = (member: TeamMember): string | null => {
    if (member.id === user?.id) return 'No podés eliminarte a vos mismo';
    if (member.role === 'admin') {
      const otherAdmin = data.some((m) => m.role === 'admin' && m.id !== member.id && m.is_active);
      if (!otherAdmin) return 'Debe haber al menos un administrador';
    }
    return null;
  };

  // ── Render ──
  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-gray-500">Administrá los miembros de tu clínica</p>
        <button
          onClick={() => setInviteOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
        >
          <UserPlus size={16} />
          Invitar miembro
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
            onClick={fetchMembers}
            className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Empty (only the current user) */}
      {!loading && !error && data.length <= 1 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX size={40} className="text-gray-300" />
          <p className="mt-4 text-sm text-gray-500">Solo hay un miembro en el equipo</p>
          <button
            onClick={() => setInviteOpen(true)}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
          >
            <UserPlus size={16} />
            Invitar miembro
          </button>
        </div>
      )}

      {/* Table */}
      {!loading && !error && data.length > 1 && (
        <div className="overflow-x-auto rounded-xl border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Nombre</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Email</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Rol</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Último acceso</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((member) => (
                <tr key={member.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">{member.name}</span>
                      {member.id === user?.id && (
                        <span className="text-xs text-gray-400">(vos)</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{member.email}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        member.role === 'admin'
                          ? 'bg-purple-50 text-purple-700'
                          : 'bg-blue-50 text-blue-700'
                      }`}
                    >
                      {roleLabels[member.role] || member.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {member.last_login
                      ? new Date(member.last_login).toLocaleDateString('es-AR', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })
                      : 'Nunca'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {canRemove(member) ? (
                      <button
                        onClick={() => setRemoveTarget(member)}
                        className="rounded-lg p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                        title="Remover"
                      >
                        <Trash2 size={16} />
                      </button>
                    ) : (
                      <span
                        className="inline-block rounded-lg p-1.5 text-gray-300 cursor-not-allowed"
                        title={removeError(member) || ''}
                      >
                        <Trash2 size={16} />
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Invite modal */}
      <InviteModal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        onInvite={handleInvite}
        saving={saving}
      />

      {/* Remove confirm */}
      <ConfirmDialog
        open={!!removeTarget}
        title="Remover miembro"
        message={
          removeTarget
            ? `¿Estás seguro de remover a ${removeTarget.name} (${removeTarget.email}) del equipo?`
            : ''
        }
        confirmLabel="Remover"
        onConfirm={handleRemove}
        onCancel={() => setRemoveTarget(null)}
        loading={deleting}
        danger
      />
    </div>
  );
}
