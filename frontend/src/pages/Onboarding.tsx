import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  CheckCircle,
  ArrowRight,
  ArrowLeft,
  SkipForward,
  Loader2,
  Stethoscope,
  Smartphone,
  Calendar,
  Building2,
  HelpCircle,
  ExternalLink,
  AlertCircle,
} from 'lucide-react';
import {
  onboarding,
  clinicConfig,
  calendar,
  faqs,
  type OnboardingStatus,
  type OnboardingStep as OnboardingStepType,
  type FAQTemplate,
  type ClinicConfig,
} from '../services/api';

// ── Progress Indicator ─────────────────────────────────────────

function ProgressDots({ steps, currentStep }: { steps: OnboardingStepType[]; currentStep: number }) {
  return (
    <div className="mb-10 flex items-center justify-center gap-1">
      {steps.map((step, index) => {
        const isCompleted = step.completed;
        const isCurrent = step.id === currentStep;
        const isLast = index === steps.length - 1;

        return (
          <div key={step.id} className="flex items-center">
            {/* Circle */}
            <div
              className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold transition-colors ${
                isCompleted
                  ? 'bg-green-500 text-white'
                  : isCurrent
                    ? 'bg-clinic-500 text-white ring-4 ring-clinic-100'
                    : 'bg-gray-200 text-gray-400'
              }`}
            >
              {isCompleted ? <CheckCircle size={20} /> : step.id}
            </div>
            {/* Connector line */}
            {!isLast && (
              <div
                className={`mx-1 h-1 w-10 sm:w-16 rounded-full ${
                  isCompleted ? 'bg-green-500' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Step 1: Conectar WhatsApp ──────────────────────────────────

function StepWhatsApp({
  onComplete,
  onSkip,
}: {
  onComplete: () => void;
  onSkip: () => void;
}) {
  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-green-100">
          <Smartphone size={32} className="text-green-600" />
        </div>
        <h2 className="text-xl font-bold text-gray-900">Conectar WhatsApp</h2>
        <p className="mt-2 text-sm text-gray-500 max-w-md">
          Conectá WhatsApp a tu clínica para que el bot pueda recibir y responder mensajes
          automáticamente.
        </p>
      </div>

      <div className="rounded-xl border bg-gray-50 p-6">
        <h3 className="mb-4 text-sm font-semibold text-gray-700">Pasos a seguir:</h3>
        <ol className="space-y-3">
          <li className="flex gap-3 text-sm text-gray-600">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-clinic-100 text-xs font-bold text-clinic-700">1</span>
            <span>Descargá la app de <strong>Evolution API</strong> o accedé al panel de administración.</span>
          </li>
          <li className="flex gap-3 text-sm text-gray-600">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-clinic-100 text-xs font-bold text-clinic-700">2</span>
            <span>Escaneá el código QR con tu WhatsApp para vincular la instancia.</span>
          </li>
          <li className="flex gap-3 text-sm text-gray-600">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-clinic-100 text-xs font-bold text-clinic-700">3</span>
            <span>Configurá el webhook hacia nuestra API para que los mensajes entrantes se procesen automáticamente.</span>
          </li>
        </ol>
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={onSkip}
          className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-gray-600 transition-colors"
        >
          <SkipForward size={16} />
          Lo haré después
        </button>
        <button
          onClick={onComplete}
          className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-clinic-600 transition-colors"
        >
          Ya conecté
          <CheckCircle size={16} />
        </button>
      </div>
    </div>
  );
}

// ── Step 2: Conectar Google Calendar ───────────────────────────

function StepGoogleCalendar({
  onComplete,
  onSkip,
  loading,
  oauthCode,
  onOauthHandled,
}: {
  onComplete: () => void;
  onSkip: () => void;
  loading: boolean;
  oauthCode: string | null;
  onOauthHandled: () => void;
}) {
  const [calendarStatus, setCalendarStatus] = useState<{ connected: boolean } | null>(null);
  const [checkingStatus, setCheckingStatus] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [oauthProcessing, setOauthProcessing] = useState(false);

  // Check current calendar status
  useEffect(() => {
    let cancelled = false;
    const fetchStatus = async () => {
      setCheckingStatus(true);
      try {
        const status = await calendar.status();
        if (!cancelled) setCalendarStatus(status);
      } catch {
        // Not connected
      } finally {
        if (!cancelled) setCheckingStatus(false);
      }
    };
    fetchStatus();
    return () => { cancelled = true; };
  }, []);

  // Handle OAuth callback
  useEffect(() => {
    if (oauthCode && !oauthProcessing) {
      setOauthProcessing(true);
      calendar
        .handleCallback(oauthCode)
        .then(async () => {
          const status = await calendar.status();
          setCalendarStatus(status);
          onOauthHandled();
        })
        .catch(() => {
          // Ignore errors, user can retry
        })
        .finally(() => setOauthProcessing(false));
    }
  }, [oauthCode]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const { url } = await calendar.getAuthUrl();
      window.location.href = url;
    } catch {
      setConnecting(false);
    }
  };

  if (checkingStatus && !calendarStatus) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={28} className="animate-spin text-clinic-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-100">
          <Calendar size={32} className="text-blue-600" />
        </div>
        <h2 className="text-xl font-bold text-gray-900">Conectar Google Calendar</h2>
        <p className="mt-2 text-sm text-gray-500 max-w-md">
          Conectá el calendario de tu clínica para que el bot pueda consultar disponibilidad y
          gestionar turnos automáticamente.
        </p>
      </div>

      {(oauthProcessing) && (
        <div className="flex items-center justify-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          <Loader2 size={18} className="animate-spin" />
          Procesando conexión con Google Calendar...
        </div>
      )}

      {calendarStatus?.connected ? (
        <div className="rounded-xl border border-green-200 bg-green-50 p-6 text-center">
          <CheckCircle size={40} className="mx-auto text-green-500" />
          <p className="mt-3 font-semibold text-green-700">Google Calendar conectado</p>
          <p className="mt-1 text-sm text-green-600">Tu calendario está sincronizado con el bot.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-6 text-center">
          <Calendar size={40} className="mx-auto text-gray-300" />
          <p className="mt-3 text-sm text-gray-500">
            Conectá tu calendario de Google para que el bot pueda gestionar turnos.
          </p>
          <button
            onClick={handleConnect}
            disabled={connecting}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
          >
            {connecting ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <ExternalLink size={16} />
            )}
            Conectar Google Calendar
          </button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <button
          onClick={onSkip}
          className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-gray-600 transition-colors"
        >
          <SkipForward size={16} />
          Lo haré después
        </button>
        <button
          onClick={onComplete}
          disabled={!calendarStatus?.connected}
          className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Continuar
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}

// ── Step 3: Configurar clínica ─────────────────────────────────

function StepClinicConfig({
  onComplete,
  onSkipToSettings,
}: {
  onComplete: () => void;
  onSkipToSettings: () => void;
}) {
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');
  const [weekdayStart, setWeekdayStart] = useState('08:00');
  const [weekdayEnd, setWeekdayEnd] = useState('18:00');
  const [satStart, setSatStart] = useState('09:00');
  const [satEnd, setSatEnd] = useState('13:00');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load existing config on mount
  useEffect(() => {
    let cancelled = false;
    clinicConfig
      .get()
      .then((config) => {
        if (cancelled) return;
        setName(config.name || '');
        setAddress(config.address || '');
        setPhone(config.phone || '');
        if (config.business_hours) {
          const bh = config.business_hours;
          // Weekdays: monday-friday
          for (const day of ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']) {
            if (bh[day] && !bh[day].closed && bh[day].start) {
              setWeekdayStart(bh[day].start);
              setWeekdayEnd(bh[day].end);
              break;
            }
          }
          if (bh['saturday'] && !bh['saturday'].closed) {
            setSatStart(bh['saturday'].start || '09:00');
            setSatEnd(bh['saturday'].end || '13:00');
          }
        }
      })
      .catch(() => {
        // No config yet, defaults are fine
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const handleSave = async () => {
    if (!name.trim()) {
      setError('El nombre de la clínica es obligatorio');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      // Build business_hours from simplified form
      const business_hours: Record<string, { start: string; end: string; closed?: boolean }> = {};
      const weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'];
      for (const day of weekdays) {
        business_hours[day] = { start: weekdayStart, end: weekdayEnd };
      }
      business_hours['saturday'] = { start: satStart, end: satEnd };
      business_hours['sunday'] = { start: '', end: '', closed: true };

      await clinicConfig.update({
        name: name.trim(),
        address: address.trim() || undefined,
        phone: phone.trim() || undefined,
        business_hours,
      });
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al guardar configuración');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={28} className="animate-spin text-clinic-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-purple-100">
          <Building2 size={32} className="text-purple-600" />
        </div>
        <h2 className="text-xl font-bold text-gray-900">Configurar clínica</h2>
        <p className="mt-2 text-sm text-gray-500 max-w-md">
          Contanos los datos básicos de tu clínica para que el bot pueda responder con información
          precisa.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      <div className="space-y-4 max-w-md mx-auto">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Nombre de la clínica *</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
            placeholder="Clínica Salud Total"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Dirección</label>
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
            placeholder="Av. Siempre Viva 123"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Teléfono</label>
          <input
            type="text"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
            placeholder="+54 11 1234-5678"
          />
        </div>

        {/* Hours */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Horarios de atención</label>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="min-w-[120px] text-sm text-gray-600">Lunes a Viernes</span>
              <input
                type="time"
                value={weekdayStart}
                onChange={(e) => setWeekdayStart(e.target.value)}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              />
              <span className="text-gray-400">a</span>
              <input
                type="time"
                value={weekdayEnd}
                onChange={(e) => setWeekdayEnd(e.target.value)}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              />
            </div>
            <div className="flex items-center gap-3">
              <span className="min-w-[120px] text-sm text-gray-600">Sábado</span>
              <input
                type="time"
                value={satStart}
                onChange={(e) => setSatStart(e.target.value)}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              />
              <span className="text-gray-400">a</span>
              <input
                type="time"
                value={satEnd}
                onChange={(e) => setSatEnd(e.target.value)}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-clinic-500 focus:outline-none focus:ring-1 focus:ring-clinic-500"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={onSkipToSettings}
          className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
        >
          Después voy a configuración avanzada
        </button>
        <button
          onClick={handleSave}
          disabled={saving || !name.trim()}
          className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
        >
          {saving ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <CheckCircle size={16} />
          )}
          Guardar y continuar
        </button>
      </div>
    </div>
  );
}

// ── Step 4: Cargar preguntas frecuentes ────────────────────────

function StepFAQTemplates({
  onComplete,
  onSkip,
}: {
  onComplete: () => void;
  onSkip: () => void;
}) {
  const [templates, setTemplates] = useState<FAQTemplate[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    onboarding
      .faqTemplates()
      .then((res) => {
        if (cancelled) return;
        setTemplates(res.templates);
        // Pre-select all by default
        setSelected(new Set(res.templates.map((_, i) => i)));
      })
      .catch(() => {
        if (!cancelled) setError('Error al cargar plantillas');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const toggle = (index: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const handleLoadSelected = async () => {
    setSaving(true);
    setError(null);
    try {
      const toCreate = templates.filter((_, i) => selected.has(i));
      // Create FAQs sequentially
      for (const tpl of toCreate) {
        await faqs.create({
          question: tpl.question,
          answer: tpl.answer,
          category: tpl.category,
        });
      }
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar las preguntas');
    } finally {
      setSaving(false);
    }
  };

  const handleLoadAll = async () => {
    setSaving(true);
    setError(null);
    try {
      for (const tpl of templates) {
        await faqs.create({
          question: tpl.question,
          answer: tpl.answer,
          category: tpl.category,
        });
      }
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar las preguntas');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={28} className="animate-spin text-clinic-500" />
      </div>
    );
  }

  if (error && templates.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col items-center text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-100">
            <HelpCircle size={32} className="text-amber-600" />
          </div>
          <h2 className="text-xl font-bold text-gray-900">Preguntas frecuentes</h2>
          <p className="mt-2 text-sm text-gray-500">{error}</p>
        </div>
        <div className="flex justify-center">
          <button onClick={onSkip} className="text-sm text-gray-400 hover:text-gray-600">
            Ahora no
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-100">
          <HelpCircle size={32} className="text-amber-600" />
        </div>
        <h2 className="text-xl font-bold text-gray-900">Preguntas frecuentes</h2>
        <p className="mt-2 text-sm text-gray-500 max-w-md">
          Cargá algunas preguntas frecuentes para que el bot pueda responder automáticamente a tus
          pacientes. Seleccioná las que quieras incluir.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      <div className="space-y-2 max-w-lg mx-auto">
        {templates.map((tpl, index) => (
          <label
            key={index}
            className={`flex items-start gap-3 rounded-lg border p-4 cursor-pointer transition-colors ${
              selected.has(index)
                ? 'border-clinic-200 bg-clinic-50'
                : 'border-gray-200 bg-white hover:bg-gray-50'
            }`}
          >
            <input
              type="checkbox"
              checked={selected.has(index)}
              onChange={() => toggle(index)}
              className="mt-0.5 rounded border-gray-300 text-clinic-500 focus:ring-clinic-500"
            />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900">{tpl.question}</p>
              <p className="mt-0.5 text-xs text-gray-500 line-clamp-2">{tpl.answer}</p>
              <span className="mt-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                {tpl.category}
              </span>
            </div>
          </label>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={onSkip}
          className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
        >
          Ahora no
        </button>
        <div className="flex gap-3">
          <button
            onClick={handleLoadAll}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg border border-clinic-200 px-4 py-2.5 text-sm font-medium text-clinic-700 hover:bg-clinic-50 transition-colors disabled:opacity-50"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : null}
            Cargar todas
          </button>
          <button
            onClick={handleLoadSelected}
            disabled={saving || selected.size === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-clinic-600 transition-colors disabled:opacity-50"
          >
            {saving ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <CheckCircle size={16} />
            )}
            Cargar seleccionadas ({selected.size})
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Step 5: Bot activo ─────────────────────────────────────────

function StepBotReady({ onGoToDashboard }: { onGoToDashboard: () => void }) {
  const steps = [
    { label: 'WhatsApp conectado', icon: Smartphone },
    { label: 'Google Calendar conectado', icon: Calendar },
    { label: 'Clínica configurada', icon: Building2 },
    { label: 'Preguntas frecuentes cargadas', icon: HelpCircle },
  ];

  return (
    <div className="space-y-8 text-center">
      <div className="flex flex-col items-center">
        <div className="mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-green-100">
          <CheckCircle size={48} className="text-green-500" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900">Bot listo para atender</h2>
        <p className="mt-2 text-sm text-gray-500 max-w-md">
          Felicitaciones, completaste todos los pasos. Tu bot ya puede recibir y responder mensajes
          de tus pacientes.
        </p>
      </div>

      <div className="mx-auto max-w-sm space-y-3">
        {steps.map((step) => {
          const Icon = step.icon;
          return (
            <div
              key={step.label}
              className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-3"
            >
              <CheckCircle size={20} className="text-green-500 shrink-0" />
              <Icon size={18} className="text-green-600 shrink-0" />
              <span className="text-sm font-medium text-green-800">{step.label}</span>
            </div>
          );
        })}
        <div className="flex items-center gap-3 rounded-lg border border-clinic-200 bg-clinic-50 px-4 py-3">
          <CheckCircle size={20} className="text-clinic-500 shrink-0" />
          <Stethoscope size={18} className="text-clinic-600 shrink-0" />
          <span className="text-sm font-medium text-clinic-800">Bot listo para atender</span>
        </div>
      </div>

      <div className="pt-4">
        <button
          onClick={onGoToDashboard}
          className="inline-flex items-center gap-2 rounded-lg bg-clinic-500 px-8 py-3 text-sm font-semibold text-white hover:bg-clinic-600 transition-colors shadow-lg shadow-clinic-200"
        >
          Ir al dashboard
          <ArrowRight size={18} />
        </button>
      </div>
    </div>
  );
}

// ── Main Onboarding Page ───────────────────────────────────────

export default function Onboarding() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [currentStep, setCurrentStep] = useState(1);
  const [error, setError] = useState<string | null>(null);

  // OAuth callback from Google Calendar
  const oauthCode = searchParams.get('code');

  // ── Load onboarding status ──
  useEffect(() => {
    let cancelled = false;
    const fetchStatus = async () => {
      setLoading(true);
      try {
        const s = await onboarding.status();
        if (cancelled) return;

        if (s.completed) {
          navigate('/dashboard', { replace: true });
          return;
        }
        setStatus(s);
        setCurrentStep(s.current_step);
      } catch {
        if (!cancelled) {
          setError('Error al verificar estado de onboarding');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchStatus();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handle OAuth callback ──
  const handleOauthHandled = () => {
    // Remove code from URL
    const params = new URLSearchParams(searchParams);
    params.delete('code');
    setSearchParams(params, { replace: true });
  };

  // ── Mark step complete ──
  const markComplete = useCallback(
    async (stepId: number) => {
      setSubmitting(true);
      try {
        const s = await onboarding.markStep(stepId);
        setStatus(s);
        if (s.completed) {
          navigate('/dashboard', { replace: true });
          return;
        }
        // Move to next incomplete step
        setCurrentStep(s.current_step);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al guardar progreso');
      } finally {
        setSubmitting(false);
      }
    },
    [navigate],
  );

  // ── Loading ──
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-clinic-50 to-blue-100">
        <Loader2 size={32} className="animate-spin text-clinic-500" />
      </div>
    );
  }

  // ── Error ──
  if (error && !status) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-clinic-50 to-blue-100 px-4">
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

  if (!status) return null;

  // ── Step actions ──
  const stepActions: Record<number, React.ReactNode> = {
    1: (
      <StepWhatsApp
        onComplete={() => markComplete(1)}
        onSkip={() => markComplete(1)}
      />
    ),
    2: (
      <StepGoogleCalendar
        onComplete={() => markComplete(2)}
        onSkip={() => markComplete(2)}
        loading={submitting}
        oauthCode={oauthCode}
        onOauthHandled={handleOauthHandled}
      />
    ),
    3: (
      <StepClinicConfig
        onComplete={() => markComplete(3)}
        onSkipToSettings={() => navigate('/settings')}
      />
    ),
    4: (
      <StepFAQTemplates
        onComplete={() => markComplete(4)}
        onSkip={() => markComplete(4)}
      />
    ),
    5: (
      <StepBotReady
        onGoToDashboard={() => {
          // Mark step 5 as complete if not already, then go to dashboard
          markComplete(5);
        }}
      />
    ),
  };

  const steps = status.steps;

  return (
    <div className="min-h-screen bg-gradient-to-br from-clinic-50 to-blue-100">
      {/* Header */}
      <div className="flex items-center justify-center pt-8 pb-4">
        <div className="flex items-center gap-2">
          <Stethoscope size={22} className="text-clinic-500" />
          <span className="text-base font-semibold text-gray-900">Configura tu clínica</span>
        </div>
      </div>

      {/* Card */}
      <div className="mx-auto max-w-2xl px-4 pb-12">
        <div className="rounded-2xl bg-white p-8 shadow-sm border">
          {/* Progress indicator */}
          <ProgressDots steps={steps} currentStep={currentStep} />

          {/* Error notification */}
          {error && (
            <div className="mb-6 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertCircle size={16} />
              {error}
              <button
                onClick={() => setError(null)}
                className="ml-auto text-red-400 hover:text-red-600"
              >
                X
              </button>
            </div>
          )}

          {/* Submitting overlay */}
          {submitting && (
            <div className="mb-6 flex items-center justify-center gap-3 rounded-lg border border-clinic-200 bg-clinic-50 px-4 py-3 text-sm text-clinic-700">
              <Loader2 size={18} className="animate-spin" />
              Guardando progreso...
            </div>
          )}

          {/* Step content */}
          {stepActions[currentStep]}

          {/* Navigation (for steps not handled internally) */}
          {currentStep > 1 && currentStep < 5 && (
            <div className="mt-8 pt-6 border-t">
              <button
                onClick={() => {
                  const prevStep = currentStep - 1;
                  setCurrentStep(prevStep);
                }}
                className="inline-flex items-center gap-2 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
              >
                <ArrowLeft size={16} />
                Anterior
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
