import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Building2,
  HelpCircle,
  Stethoscope,
  Calendar,
  Users,
  CreditCard,
  CheckCircle,
  XCircle,
  Loader2,
} from 'lucide-react';
import ClinicConfig from './ClinicConfig';
import FAQs from './FAQs';
import Doctors from './Doctors';
import CalendarIntegration from './CalendarIntegration';
import Team from './Team';
import BillingSettings from './BillingSettings';
import { calendar } from '../services/api';

// ── Tab definition ─────────────────────────────────────────────

interface Tab {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const tabs: Tab[] = [
  { id: 'clinica', label: 'Información', icon: <Building2 size={18} /> },
  { id: 'faqs', label: 'FAQs', icon: <HelpCircle size={18} /> },
  { id: 'medicos', label: 'Médicos', icon: <Stethoscope size={18} /> },
  { id: 'calendario', label: 'Calendario', icon: <Calendar size={18} /> },
  { id: 'equipo', label: 'Equipo', icon: <Users size={18} /> },
  { id: 'facturacion', label: 'Facturación', icon: <CreditCard size={18} /> },
];

// ── Notification ───────────────────────────────────────────────

function Notification({
  type,
  message,
  onClose,
}: {
  type: 'success' | 'error';
  message: string;
  onClose: () => void;
}) {
  const Icon = type === 'success' ? CheckCircle : XCircle;
  const colors =
    type === 'success'
      ? 'bg-green-50 border-green-200 text-green-700'
      : 'bg-red-50 border-red-200 text-red-700';

  return (
    <div
      className={`fixed right-6 top-6 z-50 flex items-center gap-3 rounded-lg border px-4 py-3 shadow-lg ${colors}`}
    >
      <Icon size={20} />
      <span className="text-sm font-medium">{message}</span>
      <button onClick={onClose} className="ml-2 text-current opacity-60 hover:opacity-100">
        <XCircle size={16} />
      </button>
    </div>
  );
}

// ── Settings Page ──────────────────────────────────────────────

export default function Settings() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'clinica';
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [oauthLoading, setOauthLoading] = useState(false);

  // ── Handle OAuth callback ──
  const code = searchParams.get('code');
  const calendarConnected = searchParams.get('calendar');

  useEffect(() => {
    if (code && !oauthLoading) {
      setOauthLoading(true);
      calendar
        .handleCallback(code)
        .then(() => {
          setNotification({ type: 'success', message: 'Google Calendar conectado exitosamente' });
          // Remove code from URL
          const params = new URLSearchParams(searchParams);
          params.delete('code');
          setSearchParams(params, { replace: true });
        })
        .catch((err) => {
          setNotification({
            type: 'error',
            message: err instanceof Error ? err.message : 'Error al conectar Google Calendar',
          });
        })
        .finally(() => setOauthLoading(false));
    }
  }, [code]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handle redirect from backend after OAuth ──
  useEffect(() => {
    if (calendarConnected === 'connected') {
      setNotification({ type: 'success', message: 'Google Calendar conectado exitosamente' });
      const params = new URLSearchParams(searchParams);
      params.delete('calendar');
      setSearchParams(params, { replace: true });
    }
  }, [calendarConnected]); // eslint-disable-line react-hooks/exhaustive-deps

  const setTab = (tabId: string) => {
    setSearchParams({ tab: tabId }, { replace: true });
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Configuración</h1>
        <p className="mt-1 text-sm text-gray-500">Administrá la configuración de tu clínica</p>
      </div>

      {/* Notification */}
      {notification && (
        <Notification
          type={notification.type}
          message={notification.message}
          onClose={() => setNotification(null)}
        />
      )}

      {/* OAuth loading overlay */}
      {oauthLoading && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          <Loader2 size={18} className="animate-spin" />
          Procesando conexión con Google Calendar...
        </div>
      )}

      {/* Tab bar */}
      <div className="mb-6 border-b border-gray-200">
        <nav className="flex gap-0 -mb-px">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setTab(tab.id)}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'border-clinic-500 text-clinic-600'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'clinica' && <ClinicConfig onNotification={setNotification} />}
      {activeTab === 'faqs' && <FAQs onNotification={setNotification} />}
      {activeTab === 'medicos' && <Doctors onNotification={setNotification} />}
      {activeTab === 'calendario' && <CalendarIntegration onNotification={setNotification} />}
      {activeTab === 'equipo' && <Team onNotification={setNotification} />}
      {activeTab === 'facturacion' && <BillingSettings onNotification={setNotification} />}
    </div>
  );
}
