import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Appointments from './pages/Appointments';
import AppointmentDetail from './pages/AppointmentDetail';
import Conversations from './pages/Conversations';
import ConversationDetail from './pages/ConversationDetail';
import Settings from './pages/Settings';
import Onboarding from './pages/Onboarding';

export default function App() {
  const { loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-clinic-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Protected routes — standalone (no Layout) */}
      <Route element={<ProtectedRoute />}>
        <Route path="/onboarding" element={<Onboarding />} />
      </Route>

      {/* Protected routes — with sidebar Layout */}
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/appointments" element={<Appointments />} />
          <Route path="/appointments/:id" element={<AppointmentDetail />} />
          <Route path="/conversations" element={<Conversations />} />
          <Route path="/conversations/:id" element={<ConversationDetail />} />

          {/* Settings (with tabs) */}
          <Route path="/settings" element={<Settings />} />
          {/* Team redirects to Settings → Equipo tab */}
          <Route
            path="/team"
            element={<Navigate to="/settings?tab=equipo" replace />}
          />

          {/* Placeholder routes for future pages */}
          <Route
            path="/patients"
            element={
              <div className="flex items-center justify-center py-20 text-gray-400">
                Pacientes — próximamente
              </div>
            }
          />
          <Route
            path="/faq"
            element={
              <div className="flex items-center justify-center py-20 text-gray-400">
                FAQ — próximamente
              </div>
            }
          />
        </Route>
      </Route>

      {/* Default redirects */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
