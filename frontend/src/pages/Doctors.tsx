import { useEffect, useState, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  SearchX,
  Plus,
  Edit3,
  Trash2,
  X,
  CheckCircle,
} from 'lucide-react';
import { doctors, type Doctor, type DoctorInput } from '../services/api';

// ── Props ──────────────────────────────────────────────────────

interface Props {
  onNotification: (n: { type: 'success' | 'error'; message: string }) => void;
}

// ── Modal ──────────────────────────────────────────────────────

function DoctorModal({
  open,
  editing,
  onClose,
  onSave,
  saving,
}: {
  open: boolean;
  editing: Doctor | null;
  onClose: () => void;
  onSave: (data: DoctorInput) => void;
  saving: boolean;
}) {
  const [name, setName] = useState('');
  const [specialty, setSpecialty] = useState('');
  const [calendarId, setCalendarId] = useState('');

  useEffect(() => {
    if (editing) {
      setName(editing.name);
      setSpecialty(editing.specialty || 'Medicina General');
      setCalendarId(editing.calendar_id || '');
    } else {
      setName('');
      setSpecialty('Medicina General');
      setCalendarId('');
    }
  }, [editing, open]);

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSave({
      name: name.trim(),
      specialty: specialty.trim(),
      calendar_id: calendarId.trim() || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">
            {editing ? 'Editar médico' : 'Agregar médico'}
          </h3>
          <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nombre</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              placeholder="Dr. Juan García"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Especialidad</label>
            <input
              type="text"
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              placeholder="Medicina General"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Google Calendar ID <span className="text-gray-400 font-normal">(opcional)</span>
            </label>
            <input
              type="text"
              value={calendarId}
              onChange={(e) => setCalendarId(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              placeholder="ej: juan.garcia@gmail.com"
            />
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
              disabled={saving || !name.trim()}
              className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
            >
              {saving && <Loader2 size={16} className="animate-spin" />}
              {editing ? 'Guardar cambios' : 'Agregar'}
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

// ── Doctors Page ───────────────────────────────────────────────

export default function DoctorsPage({ onNotification }: Props) {
  const [data, setData] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Doctor | null>(null);
  const [saving, setSaving] = useState(false);

  // Delete
  const [deleteTarget, setDeleteTarget] = useState<Doctor | null>(null);
  const [deleting, setDeleting] = useState(false);

  // ── Fetch ──
  const fetchDoctors = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await doctors.list();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar médicos');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDoctors();
  }, [fetchDoctors]);

  // ── Save ──
  const handleSave = async (input: DoctorInput) => {
    setSaving(true);
    try {
      if (editing) {
        await doctors.update(editing.id, input);
        onNotification({ type: 'success', message: 'Médico actualizado correctamente' });
      } else {
        await doctors.create(input);
        onNotification({ type: 'success', message: 'Médico agregado correctamente' });
      }
      setModalOpen(false);
      setEditing(null);
      fetchDoctors();
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al guardar médico',
      });
    } finally {
      setSaving(false);
    }
  };

  // ── Delete ──
  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await doctors.remove(deleteTarget.id);
      onNotification({ type: 'success', message: 'Médico eliminado correctamente' });
      setDeleteTarget(null);
      fetchDoctors();
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al eliminar médico',
      });
    } finally {
      setDeleting(false);
    }
  };

  // ── Render ──
  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-gray-500">Administrá los profesionales de tu clínica</p>
        <button
          onClick={() => { setEditing(null); setModalOpen(true); }}
          className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
        >
          <Plus size={16} />
          Agregar médico
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
            onClick={fetchDoctors}
            className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && data.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX size={40} className="text-gray-300" />
          <p className="mt-4 text-sm text-gray-500">No hay médicos registrados</p>
          <button
            onClick={() => { setEditing(null); setModalOpen(true); }}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
          >
            <Plus size={16} />
            Agregar primer médico
          </button>
        </div>
      )}

      {/* Table */}
      {!loading && !error && data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Nombre</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Especialidad</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Estado</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((doc) => (
                <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">{doc.name}</td>
                  <td className="px-4 py-3 text-gray-600">{doc.specialty || 'Medicina General'}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        doc.is_active
                          ? 'bg-green-50 text-green-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {doc.calendar_id ? (
                        <><CheckCircle size={12} /> Conectado</>
                      ) : (
                        'Sin calendario'
                      )}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => { setEditing(doc); setModalOpen(true); }}
                        className="rounded-lg p-1.5 text-gray-400 hover:bg-blue-50 hover:text-blue-600 transition-colors"
                        title="Editar"
                      >
                        <Edit3 size={16} />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(doc)}
                        className="rounded-lg p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                        title="Eliminar"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      <DoctorModal
        open={modalOpen}
        editing={editing}
        onClose={() => { setModalOpen(false); setEditing(null); }}
        onSave={handleSave}
        saving={saving}
      />

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Eliminar médico"
        message={`¿Estás seguro de eliminar a ${deleteTarget?.name}? Esta acción no se puede deshacer.`}
        confirmLabel="Eliminar"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
        loading={deleting}
      />
    </div>
  );
}
