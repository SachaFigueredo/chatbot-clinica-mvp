import { useEffect, useState } from 'react';
import {
  Loader2,
  AlertCircle,
  Save,
  CheckCircle,
} from 'lucide-react';
import { clinicConfig, type ClinicConfig } from '../services/api';

// ── Types ──────────────────────────────────────────────────────

interface DayHoursForm {
  start: string;
  end: string;
  closed: boolean;
}

type DayGroup = 'weekdays' | 'saturday' | 'sunday';

const dayGroupLabels: Record<DayGroup, string> = {
  weekdays: 'Lunes a Viernes',
  saturday: 'Sábado',
  sunday: 'Domingo',
};

const dayGroupMap: Record<DayGroup, string[]> = {
  weekdays: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
  saturday: ['saturday'],
  sunday: ['sunday'],
};

// ── Props ──────────────────────────────────────────────────────

interface Props {
  onNotification: (n: { type: 'success' | 'error'; message: string }) => void;
}

// ── Component ──────────────────────────────────────────────────

export default function ClinicConfigForm({ onNotification }: Props) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form fields
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [duration, setDuration] = useState(20);
  const [particularPrice, setParticularPrice] = useState(0);
  const [obrasPrice, setObrasPrice] = useState(0);
  const [welcomeMessage, setWelcomeMessage] = useState('');

  // Business hours
  const [hours, setHours] = useState<Record<DayGroup, DayHoursForm>>({
    weekdays: { start: '08:00', end: '17:00', closed: false },
    saturday: { start: '09:00', end: '13:00', closed: true },
    sunday: { start: '', end: '', closed: true },
  });

  // ── Load ──
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    clinicConfig
      .get()
      .then((config) => {
        if (cancelled) return;
        setName(config.name || '');
        setAddress(config.address || '');
        setPhone(config.phone || '');
        setEmail(config.email || '');
        setDuration(config.appointment_duration_minutes || 20);
        setParticularPrice(config.prices?.particular || 0);
        setObrasPrice(config.prices?.obras_sociales || 0);
        setWelcomeMessage(config.welcome_message || '');

        // Map business_hours to form groups
        const bh = config.business_hours || {};
        const newHours = { ...hours };

        // Weekdays: take the first weekday that has data
        const weekday = dayGroupMap.weekdays
          .map((d) => bh[d])
          .find((h) => h && !h.closed && (h.start || h.end));
        if (weekday) {
          newHours.weekdays = { start: weekday.start || '08:00', end: weekday.end || '17:00', closed: false };
        } else if (dayGroupMap.weekdays.some((d) => bh[d]?.closed)) {
          newHours.weekdays = { start: '08:00', end: '17:00', closed: true };
        }

        const sat = bh['saturday'];
        if (sat) {
          newHours.saturday = {
            start: sat.start || '09:00',
            end: sat.end || '13:00',
            closed: sat.closed || false,
          };
        }
        const sun = bh['sunday'];
        if (sun) {
          newHours.sunday = {
            start: sun.start || '',
            end: sun.end || '',
            closed: sun.closed || true,
          };
        }

        setHours(newHours);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Error al cargar configuración');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Save ──
  const handleSave = async () => {
    setSaving(true);
    try {
      // Build business_hours from form groups
      const business_hours: Record<string, { start: string; end: string; closed?: boolean }> = {};

      for (const [group, fields] of Object.entries(hours) as [DayGroup, DayHoursForm][]) {
        for (const day of dayGroupMap[group]) {
          if (fields.closed || !fields.start || !fields.end) {
            business_hours[day] = { start: '', end: '', closed: true };
          } else {
            business_hours[day] = { start: fields.start, end: fields.end };
          }
        }
      }

      const payload: Partial<ClinicConfig> = {
        name,
        address,
        phone,
        email,
        business_hours,
        appointment_duration_minutes: duration,
        prices: { particular: particularPrice, obras_sociales: obrasPrice },
        welcome_message: welcomeMessage,
      };

      await clinicConfig.update(payload);
      onNotification({ type: 'success', message: 'Configuración guardada correctamente' });
    } catch (err) {
      onNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Error al guardar configuración',
      });
    } finally {
      setSaving(false);
    }
  };

  // ── Hours handler ──
  const updateHours = (group: DayGroup, field: keyof DayHoursForm, value: boolean | string) => {
    setHours((prev) => ({
      ...prev,
      [group]: { ...prev[group], [field]: value },
    }));
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
  if (error) {
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

  // ── Render ──
  return (
    <div className="max-w-2xl">
      {/* Basic info */}
      <section className="mb-8">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Información de la clínica</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nombre de la clínica</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              placeholder="Mi Clínica"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Dirección</label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              placeholder="Av. Siempre Viva 123"
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Teléfono</label>
              <input
                type="text"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
                placeholder="+54 11 1234-5678"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
                placeholder="contacto@miclinica.com"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Business hours */}
      <section className="mb-8">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Horarios de atención</h2>
        <div className="space-y-4">
          {(Object.keys(dayGroupLabels) as DayGroup[]).map((group) => (
            <div key={group} className="rounded-lg border bg-gray-50 p-4">
              <div className="flex flex-wrap items-center gap-4">
                <span className="min-w-[140px] text-sm font-medium text-gray-700">
                  {dayGroupLabels[group]}
                </span>
                <label className="flex items-center gap-2 text-sm text-gray-600">
                  <input
                    type="checkbox"
                    checked={hours[group].closed}
                    onChange={(e) => updateHours(group, 'closed', e.target.checked)}
                    className="rounded border-gray-300 text-clinic-500 focus:ring-clinic-500"
                  />
                  Cerrado
                </label>
                {!hours[group].closed && (
                  <div className="flex items-center gap-2">
                    <input
                      type="time"
                      value={hours[group].start}
                      onChange={(e) => updateHours(group, 'start', e.target.value)}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
                    />
                    <span className="text-gray-400">a</span>
                    <input
                      type="time"
                      value={hours[group].end}
                      onChange={(e) => updateHours(group, 'end', e.target.value)}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
                    />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Duration & Prices */}
      <section className="mb-8">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Duración y precios</h2>
        <div className="space-y-4">
          <div className="max-w-xs">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Duración del turno (minutos)
            </label>
            <input
              type="number"
              min={5}
              max={120}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Precio particular ($)
              </label>
              <input
                type="number"
                min={0}
                value={particularPrice}
                onChange={(e) => setParticularPrice(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Precio obras sociales ($)
              </label>
              <input
                type="number"
                min={0}
                value={obrasPrice}
                onChange={(e) => setObrasPrice(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Welcome message */}
      <section className="mb-8">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Mensaje de bienvenida</h2>
        <div>
          <textarea
            value={welcomeMessage}
            onChange={(e) => setWelcomeMessage(e.target.value)}
            rows={4}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
            placeholder="¡Hola! Soy el asistente virtual de {clinic_name}. ¿En qué puedo ayudarte?"
          />
          <p className="mt-1 text-xs text-gray-400">
            Usá {'{clinic_name}'} para insertar el nombre de la clínica automáticamente.
          </p>
        </div>
      </section>

      {/* Save button */}
      <div className="flex justify-end border-t pt-6">
        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          Guardar configuración
        </button>
      </div>
    </div>
  );
}
