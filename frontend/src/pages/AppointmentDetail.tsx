import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Loader2,
  AlertCircle,
  ArrowLeft,
  Calendar,
  Clock,
  User,
  Phone,
  Stethoscope,
  FileText,
  XCircle,
  CheckCircle,
  UserCheck,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { appointments, type Appointment, type AppointmentStatus } from '../services/api';

// ── Helpers ────────────────────────────────────────────────────

const statusLabels: Record<AppointmentStatus, string> = {
  pending: 'Pendiente',
  confirmed: 'Confirmado',
  cancelled_by_patient: 'Cancelado por paciente',
  cancelled_by_clinic: 'Cancelado por clínica',
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

function formatDateTime(iso: string) {
  const d = parseISO(iso);
  return {
    date: format(d, "EEEE d 'de' MMMM 'de' yyyy", { locale: es }),
    time: format(d, 'HH:mm', { locale: es }),
  };
}

function formatDateTimeShort(iso: string) {
  const d = parseISO(iso);
  return format(d, "d 'de' MMM '·' HH:mm", { locale: es });
}

// ── Confirm Dialog ─────────────────────────────────────────────

function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  confirmColor = 'bg-red-500 hover:bg-red-600',
  onConfirm,
  onCancel,
  loading,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  confirmColor?: string;
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
            Volver
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50 flex items-center gap-2 ${confirmColor}`}
          >
            {loading && <Loader2 size={16} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Appointment Detail Page ────────────────────────────────────

export default function AppointmentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [appointment, setAppointment] = useState<Appointment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<'cancel' | 'confirm' | 'attended' | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // ── Fetch ──
  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    appointments
      .get(id)
      .then(setAppointment)
      .catch((err) => setError(err instanceof Error ? err.message : 'Turno no encontrado'))
      .finally(() => setLoading(false));
  }, [id]);

  // ── Actions ──
  const handleAction = async () => {
    if (!id || !action) return;
    setActionLoading(true);
    try {
      let result: Appointment;
      switch (action) {
        case 'cancel':
          result = await appointments.cancel(id);
          break;
        case 'confirm':
          result = await appointments.confirm(id);
          break;
        case 'attended':
          result = await appointments.markAttended(id);
          break;
      }
      setAppointment(result!);
      setAction(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Error al ejecutar acción');
    } finally {
      setActionLoading(false);
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
  if (error || !appointment) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <AlertCircle size={40} className="text-red-400" />
        <p className="mt-4 text-sm text-gray-600">{error || 'Turno no encontrado'}</p>
        <button
          onClick={() => navigate('/appointments')}
          className="mt-4 rounded-lg bg-clinic-500 px-4 py-2 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
        >
          Volver a turnos
        </button>
      </div>
    );
  }

  const { date, time } = formatDateTime(appointment.start_time);
  const endTime = format(appointment.end_time ? parseISO(appointment.end_time) : parseISO(appointment.start_time), 'HH:mm', { locale: es });

  return (
    <div>
      {/* Back button */}
      <button
        onClick={() => navigate('/appointments')}
        className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
      >
        <ArrowLeft size={18} />
        Volver a turnos
      </button>

      {/* Card */}
      <div className="max-w-2xl">
        <div className="rounded-xl border bg-white shadow-sm">
          {/* Header */}
          <div className="flex items-center justify-between border-b px-6 py-4">
            <h1 className="text-lg font-bold text-gray-900">Detalle del turno</h1>
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${statusColors[appointment.status]}`}
            >
              {statusLabels[appointment.status]}
            </span>
          </div>

          {/* Content */}
          <div className="space-y-5 px-6 py-5">
            {/* Patient */}
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-blue-50 p-2 text-blue-500">
                <User size={20} />
              </div>
              <div>
                <p className="text-sm text-gray-500">Paciente</p>
                <p className="font-medium text-gray-900">
                  {appointment.patient.name || 'Sin nombre'}
                </p>
              </div>
            </div>

            {/* Phone */}
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-gray-50 p-2 text-gray-400">
                <Phone size={20} />
              </div>
              <div>
                <p className="text-sm text-gray-500">Teléfono</p>
                <p className="font-medium text-gray-900">{appointment.patient.phone_number}</p>
              </div>
            </div>

            {/* Doctor */}
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-green-50 p-2 text-green-500">
                <Stethoscope size={20} />
              </div>
              <div>
                <p className="text-sm text-gray-500">Médico</p>
                <p className="font-medium text-gray-900">
                  {appointment.doctor?.name || 'No asignado'}
                </p>
                {appointment.doctor?.specialty && (
                  <p className="text-sm text-gray-500">{appointment.doctor.specialty}</p>
                )}
              </div>
            </div>

            {/* Date */}
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-purple-50 p-2 text-purple-500">
                <Calendar size={20} />
              </div>
              <div>
                <p className="text-sm text-gray-500">Fecha</p>
                <p className="font-medium text-gray-900 capitalize">{date}</p>
              </div>
            </div>

            {/* Time */}
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-orange-50 p-2 text-orange-500">
                <Clock size={20} />
              </div>
              <div>
                <p className="text-sm text-gray-500">Horario</p>
                <p className="font-medium text-gray-900">
                  {time} — {endTime}
                </p>
              </div>
            </div>

            {/* Reason */}
            {appointment.reason && (
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-gray-50 p-2 text-gray-400">
                  <FileText size={20} />
                </div>
                <div>
                  <p className="text-sm text-gray-500">Motivo</p>
                  <p className="font-medium text-gray-900">{appointment.reason}</p>
                </div>
              </div>
            )}

            {/* Created at */}
            <div className="border-t pt-4">
              <p className="text-xs text-gray-400">
                Creado el {formatDateTimeShort(appointment.created_at)}
              </p>
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-3 border-t px-6 py-4">
            <button
              onClick={() => navigate('/appointments')}
              className="rounded-lg border bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Volver a lista
            </button>

            {appointment.status === 'pending' && (
              <button
                onClick={() => setAction('confirm')}
                className="inline-flex items-center gap-2 rounded-lg bg-green-500 px-4 py-2 text-sm font-medium text-white hover:bg-green-600 transition-colors"
              >
                <CheckCircle size={16} />
                Confirmar
              </button>
            )}

            {(appointment.status === 'pending' || appointment.status === 'confirmed') && (
              <>
                <button
                  onClick={() => setAction('attended')}
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-600 transition-colors"
                >
                  <UserCheck size={16} />
                  Marcar atendido
                </button>
                <button
                  onClick={() => setAction('cancel')}
                  className="inline-flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 transition-colors"
                >
                  <XCircle size={16} />
                  Cancelar
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Confirm Dialog */}
      <ConfirmDialog
        open={action === 'cancel'}
        title="Cancelar turno"
        message={`¿Estás seguro de cancelar el turno de ${appointment.patient.name || appointment.patient.phone_number}?`}
        confirmLabel="Cancelar turno"
        onConfirm={handleAction}
        onCancel={() => setAction(null)}
        loading={actionLoading}
      />
      <ConfirmDialog
        open={action === 'confirm'}
        title="Confirmar turno"
        message={`¿Confirmar el turno de ${appointment.patient.name || appointment.patient.phone_number}?`}
        confirmLabel="Confirmar"
        confirmColor="bg-green-500 hover:bg-green-600"
        onConfirm={handleAction}
        onCancel={() => setAction(null)}
        loading={actionLoading}
      />
      <ConfirmDialog
        open={action === 'attended'}
        title="Marcar como atendido"
        message={`¿Marcar como atendido el turno de ${appointment.patient.name || appointment.patient.phone_number}?`}
        confirmLabel="Atendido"
        confirmColor="bg-blue-500 hover:bg-blue-600"
        onConfirm={handleAction}
        onCancel={() => setAction(null)}
        loading={actionLoading}
      />
    </div>
  );
}
