import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Calendar,
  Download,
  Filter,
  Loader2,
  AlertCircle,
  SearchX,
  CheckCircle,
  XCircle,
  Clock,
  UserCheck,
  ChevronRight,
  Ban,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { appointments, type Appointment, type AppointmentStatus } from '../services/api';

// ── Helpers ────────────────────────────────────────────────────

const statusLabels: Record<AppointmentStatus, string> = {
  pending: 'Pendiente',
  confirmed: 'Confirmado',
  cancelled_by_patient: 'Cancelado',
  cancelled_by_clinic: 'Cancelado',
  rescheduled: 'Reprogramado',
  unconfirmed: 'Sin confirmar',
  attended: 'Atendido',
  no_show: 'No show',
};

const statusColors: Record<AppointmentStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-700',
  confirmed: 'bg-green-100 text-green-700',
  cancelled_by_patient: 'bg-red-100 text-red-700',
  cancelled_by_clinic: 'bg-red-100 text-red-700',
  rescheduled: 'bg-blue-100 text-blue-700',
  unconfirmed: 'bg-gray-100 text-gray-600',
  attended: 'bg-green-100 text-green-700',
  no_show: 'bg-gray-100 text-gray-600',
};

const statusFilterOptions: { label: string; value: string }[] = [
  { label: 'Todos', value: '' },
  { label: 'Pendiente', value: 'pending' },
  { label: 'Confirmado', value: 'confirmed' },
  { label: 'Cancelado', value: 'cancelled_by_patient' },
  { label: 'Atendido', value: 'attended' },
  { label: 'Reprogramado', value: 'rescheduled' },
];

function formatDateTime(iso: string) {
  const d = parseISO(iso);
  return {
    date: format(d, 'EEEE d MMM', { locale: es }),
    time: format(d, 'HH:mm', { locale: es }),
  };
}

function formatDateInput(iso: string) {
  return format(parseISO(iso), 'yyyy-MM-dd');
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
            className="rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {loading && <Loader2 size={16} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Appointments Page ──────────────────────────────────────────

export default function Appointments() {
  const navigate = useNavigate();
  const [data, setData] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const today = formatDateInput(new Date().toISOString());
  const [filterDate, setFilterDate] = useState(today);
  const [filterStatus, setFilterStatus] = useState('');

  // Confirm dialog
  const [dialog, setDialog] = useState<{
    open: boolean;
    action: 'cancel' | 'confirm' | 'attended';
    appointmentId: string;
    patientName: string;
  }>({ open: false, action: 'cancel', appointmentId: '', patientName: '' });
  const [actionLoading, setActionLoading] = useState(false);

  // ── Fetch ──
  const fetchAppointments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await appointments.list({
        date: filterDate,
        status: filterStatus || undefined,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar turnos');
    } finally {
      setLoading(false);
    }
  }, [filterDate, filterStatus]);

  useEffect(() => {
    fetchAppointments();
  }, [fetchAppointments]);

  // ── Actions ──
  const handleAction = async () => {
    if (!dialog.open) return;
    setActionLoading(true);
    try {
      switch (dialog.action) {
        case 'cancel':
          await appointments.cancel(dialog.appointmentId);
          break;
        case 'confirm':
          await appointments.confirm(dialog.appointmentId);
          break;
        case 'attended':
          await appointments.markAttended(dialog.appointmentId);
          break;
      }
      setDialog({ ...dialog, open: false });
      fetchAppointments();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Error al ejecutar acción');
    } finally {
      setActionLoading(false);
    }
  };

  const openDialog = (
    action: 'cancel' | 'confirm' | 'attended',
    appointmentId: string,
    patientName: string,
  ) => {
    setDialog({ open: true, action, appointmentId, patientName });
  };

  // ── CSV Export ──
  const handleExport = async () => {
    try {
      const blob = await appointments.exportCsv({ date: filterDate });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `turnos-${filterDate}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Error al exportar');
    }
  };

  // ── Dialog messages ──
  const dialogConfig = {
    cancel: {
      title: 'Cancelar turno',
      message: `¿Estás seguro de cancelar el turno de ${dialog.patientName}?`,
      confirmLabel: 'Cancelar turno',
    },
    confirm: {
      title: 'Confirmar turno',
      message: `¿Confirmar el turno de ${dialog.patientName}?`,
      confirmLabel: 'Confirmar',
    },
    attended: {
      title: 'Marcar como atendido',
      message: `¿Marcar como atendido el turno de ${dialog.patientName}?`,
      confirmLabel: 'Atendido',
    },
  };

  // ── Render ──
  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Turnos</h1>
          <p className="mt-1 text-sm text-gray-500">Gestioná los turnos de tu clínica</p>
        </div>
        <button
          onClick={handleExport}
          className="inline-flex items-center gap-2 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          <Download size={16} />
          Exportar CSV
        </button>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-gray-400" />
          <input
            type="date"
            value={filterDate}
            onChange={(e) => setFilterDate(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
          />
        </div>
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
            onClick={fetchAppointments}
            className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && data.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <SearchX size={40} className="text-gray-300" />
          <p className="mt-4 text-sm text-gray-500">No hay turnos para esta fecha</p>
        </div>
      )}

      {/* Table */}
      {!loading && !error && data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Paciente</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Médico</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Fecha</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Hora</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Estado</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((apt) => {
                const { date, time } = formatDateTime(apt.start_time);
                return (
                  <tr key={apt.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {apt.patient.name || apt.patient.phone_number}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {apt.doctor?.name || '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-600 capitalize">{date}</td>
                    <td className="px-4 py-3 text-gray-600">{time}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColors[apt.status]}`}
                      >
                        {statusLabels[apt.status]}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => navigate(`/appointments/${apt.id}`)}
                          className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-clinic-600 transition-colors"
                          title="Ver detalle"
                        >
                          <ChevronRight size={18} />
                        </button>
                        {apt.status === 'pending' && (
                          <button
                            onClick={() => openDialog('confirm', apt.id, apt.patient.name || apt.patient.phone_number)}
                            className="rounded-lg p-1.5 text-gray-400 hover:bg-green-50 hover:text-green-600 transition-colors"
                            title="Confirmar"
                          >
                            <CheckCircle size={18} />
                          </button>
                        )}
                        {(apt.status === 'pending' || apt.status === 'confirmed') && (
                          <>
                            <button
                              onClick={() => openDialog('cancel', apt.id, apt.patient.name || apt.patient.phone_number)}
                              className="rounded-lg p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                              title="Cancelar"
                            >
                              <XCircle size={18} />
                            </button>
                            <button
                              onClick={() => openDialog('attended', apt.id, apt.patient.name || apt.patient.phone_number)}
                              className="rounded-lg p-1.5 text-gray-400 hover:bg-blue-50 hover:text-blue-600 transition-colors"
                              title="Marcar atendido"
                            >
                              <UserCheck size={18} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Confirm Dialog */}
      <ConfirmDialog
        open={dialog.open}
        title={dialogConfig[dialog.action].title}
        message={dialogConfig[dialog.action].message}
        confirmLabel={dialogConfig[dialog.action].confirmLabel}
        onConfirm={handleAction}
        onCancel={() => setDialog({ ...dialog, open: false })}
        loading={actionLoading}
      />
    </div>
  );
}
