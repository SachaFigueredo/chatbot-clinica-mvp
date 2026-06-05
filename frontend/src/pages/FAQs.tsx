import { useEffect, useState, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  SearchX,
  Plus,
  Search,
  Edit3,
  Trash2,
  X,
  CheckCircle,
} from 'lucide-react';
import { faqs, type FAQ, type FAQInput } from '../services/api';

// ── Props ──────────────────────────────────────────────────────

interface Props {
  onNotification: (n: { type: 'success' | 'error'; message: string }) => void;
}

// ── Categories ─────────────────────────────────────────────────

const categories = ['general', 'horarios', 'precios', 'preparacion', 'contacto', 'otros'];

const categoryLabels: Record<string, string> = {
  general: 'General',
  horarios: 'Horarios',
  precios: 'Precios',
  preparacion: 'Preparación',
  contacto: 'Contacto',
  otros: 'Otros',
};

// ── Modal ──────────────────────────────────────────────────────

function FaqModal({
  open,
  editing,
  onClose,
  onSave,
  saving,
}: {
  open: boolean;
  editing: FAQ | null;
  onClose: () => void;
  onSave: (data: FAQInput) => void;
  saving: boolean;
}) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [category, setCategory] = useState('general');

  useEffect(() => {
    if (editing) {
      setQuestion(editing.question);
      setAnswer(editing.answer);
      setCategory(editing.category);
    } else {
      setQuestion('');
      setAnswer('');
      setCategory('general');
    }
  }, [editing, open]);

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !answer.trim()) return;
    onSave({ question: question.trim(), answer: answer.trim(), category });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">
            {editing ? 'Editar FAQ' : 'Agregar FAQ'}
          </h3>
          <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pregunta</label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              placeholder="¿Cuál es el horario de atención?"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Respuesta</label>
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              rows={4}
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              placeholder="Nuestro horario de atención es..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Categoría</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
            >
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {categoryLabels[cat]}
                </option>
              ))}
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
              disabled={saving || !question.trim() || !answer.trim()}
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

// ── FAQs Page ──────────────────────────────────────────────────

export default function FAQsPage({ onNotification }: Props) {
  const [data, setData] = useState<FAQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<FAQ | null>(null);
  const [saving, setSaving] = useState(false);

  // Delete dialog
  const [deleteTarget, setDeleteTarget] = useState<FAQ | null>(null);
  const [deleting, setDeleting] = useState(false);

  // ── Fetch ──
  const fetchFaqs = useCallback(async (searchTerm?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await faqs.list(searchTerm || undefined);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar FAQs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFaqs();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Search with debounce ──
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchFaqs(search);
    }, 400);
    return () => clearTimeout(timer);
  }, [search]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Save (create / update) ──
  const handleSave = async (input: FAQInput) => {
    setSaving(true);
    try {
      if (editing) {
        await faqs.update(editing.id, input);
        onNotification({ type: 'success', message: 'FAQ actualizada correctamente' });
      } else {
        await faqs.create(input);
        onNotification({ type: 'success', message: 'FAQ creada correctamente' });
      }
      setModalOpen(false);
      setEditing(null);
      fetchFaqs(search);
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al guardar FAQ',
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
      await faqs.remove(deleteTarget.id);
      onNotification({ type: 'success', message: 'FAQ eliminada correctamente' });
      setDeleteTarget(null);
      fetchFaqs(search);
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al eliminar FAQ',
      });
    } finally {
      setDeleting(false);
    }
  };

  const openEdit = (faq: FAQ) => {
    setEditing(faq);
    setModalOpen(true);
  };

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  // ── Render ──
  return (
    <div>
      {/* Header + Add button */}
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-gray-500">Gestioná las preguntas frecuentes de tu clínica</p>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
        >
          <Plus size={16} />
          Agregar FAQ
        </button>
      </div>

      {/* Search */}
      <div className="mb-4">
        <div className="relative max-w-sm">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar FAQs..."
            className="w-full rounded-lg border border-gray-300 py-2 pl-10 pr-3 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
          />
        </div>
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
            onClick={() => fetchFaqs(search)}
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
          <p className="mt-4 text-sm text-gray-500">
            {search ? 'No hay FAQs que coincidan con tu búsqueda' : 'No hay FAQs configuradas'}
          </p>
          {!search && (
            <button
              onClick={openCreate}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
            >
              <Plus size={16} />
              Agregar primera FAQ
            </button>
          )}
        </div>
      )}

      {/* Table */}
      {!loading && !error && data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Pregunta</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Categoría</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((faq) => (
                <tr key={faq.id} className="hover:bg-gray-50 transition-colors">
                  <td className="max-w-md px-4 py-3">
                    <p className="font-medium text-gray-900 truncate">{faq.question}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-block rounded-full bg-clinic-50 px-2.5 py-0.5 text-xs font-medium text-clinic-700">
                      {categoryLabels[faq.category] || faq.category}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => openEdit(faq)}
                        className="rounded-lg p-1.5 text-gray-400 hover:bg-blue-50 hover:text-blue-600 transition-colors"
                        title="Editar"
                      >
                        <Edit3 size={16} />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(faq)}
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
      <FaqModal
        open={modalOpen}
        editing={editing}
        onClose={() => { setModalOpen(false); setEditing(null); }}
        onSave={handleSave}
        saving={saving}
      />

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Eliminar FAQ"
        message={`¿Estás seguro de eliminar la FAQ "${deleteTarget?.question}"? Se eliminará de forma permanente.`}
        confirmLabel="Eliminar"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
        loading={deleting}
      />
    </div>
  );
}
