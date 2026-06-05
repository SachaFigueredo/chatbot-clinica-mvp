import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Calendar,
  Users,
  MessageSquare,
  HelpCircle,
  Settings,
  UserPlus,
  LogOut,
  Menu,
  X,
  Stethoscope,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

// ── Navigation items ───────────────────────────────────────────

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

const navItems: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
  { to: '/appointments', label: 'Turnos', icon: <Calendar size={20} /> },
  { to: '/patients', label: 'Pacientes', icon: <Users size={20} />, adminOnly: true },
  { to: '/conversations', label: 'Conversaciones', icon: <MessageSquare size={20} /> },
  { to: '/faq', label: 'FAQ', icon: <HelpCircle size={20} />, adminOnly: true },
  { to: '/settings', label: 'Configuración', icon: <Settings size={20} />, adminOnly: true },
  { to: '/team', label: 'Equipo', icon: <UserPlus size={20} />, adminOnly: true },
];

// ── Component ──────────────────────────────────────────────────

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isAdmin = user?.role === 'admin';

  const visibleItems = navItems.filter(
    (item) => !item.adminOnly || isAdmin,
  );

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
      isActive
        ? 'bg-clinic-50 text-clinic-700'
        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
    }`;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-white shadow-sm transition-transform duration-200 lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 border-b px-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-clinic-500 text-white">
            <Stethoscope size={20} />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-gray-900">Mi Clínica</p>
            <p className="text-xs text-gray-500">Panel de gestión</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/dashboard'}
              className={linkClass}
              onClick={() => setSidebarOpen(false)}
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User area */}
        <div className="border-t px-4 py-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-clinic-100 text-sm font-semibold text-clinic-700">
              {user?.name?.charAt(0).toUpperCase() || '?'}
            </div>
            <div className="leading-tight">
              <p className="text-sm font-medium text-gray-900 truncate max-w-[160px]">
                {user?.name || 'Usuario'}
              </p>
              <p className="text-xs capitalize text-gray-500">
                {user?.role === 'admin' ? 'Administrador' : 'Recepcionista'}
              </p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 hover:bg-red-50 hover:text-red-600 transition-colors"
          >
            <LogOut size={18} />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header */}
        <header className="flex h-16 items-center gap-4 border-b bg-white px-4 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-2 text-gray-600 hover:bg-gray-100"
          >
            {sidebarOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
          <div className="flex items-center gap-2">
            <Stethoscope size={18} className="text-clinic-500" />
            <span className="text-sm font-semibold text-gray-900">Mi Clínica</span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
