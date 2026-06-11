const TOKEN_KEY = 'clinic_auth_token';
const BASE_URL = '/api/v1';

// ── Types ──────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'recepcionista' | 'super_admin';
  tenant_id: string;
  is_active: boolean;
  plan?: string;
  status?: string;
  trial_ends_at?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  clinic_name: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user?: User;
}

export interface DashboardStats {
  appointments_today: number;
  pending_confirmations: number;
  active_conversations: number;
  escalated_conversations: number;
  no_show_rate: number;
}

// ── Appointment types ──────────────────────────────────────────

export type AppointmentStatus =
  | 'pending'
  | 'confirmed'
  | 'cancelled_by_patient'
  | 'cancelled_by_clinic'
  | 'rescheduled'
  | 'unconfirmed'
  | 'attended'
  | 'no_show';

export interface PatientSummary {
  id: string;
  name: string;
  phone_number: string;
}

export interface DoctorSummary {
  id: string;
  name: string;
  specialty: string;
}

export interface Appointment {
  id: string;
  patient: PatientSummary;
  doctor: DoctorSummary | null;
  status: AppointmentStatus;
  start_time: string;
  end_time: string;
  reason: string | null;
  created_at: string;
}

export interface AppointmentListParams {
  date?: string;
  doctor_id?: string;
  status?: string;
}

// ── Conversation types ─────────────────────────────────────────

export type ConversationStatus = 'active' | 'escalated' | 'resolved' | 'archived';
export type ConversationChannel = 'whatsapp' | 'web';
export type MessageOrigin = 'patient' | 'bot' | 'human';

export interface Conversation {
  id: string;
  patient: PatientSummary;
  status: ConversationStatus;
  channel: ConversationChannel;
  last_message: string | null;
  last_message_at: string | null;
  escalated_to: { id: string; name: string } | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  origin: MessageOrigin;
  content: string;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  patient: PatientSummary;
  status: ConversationStatus;
  channel: ConversationChannel;
  escalated_to: { id: string; name: string } | null;
  messages: ConversationMessage[];
  created_at: string;
  updated_at: string;
}

export interface ConversationListParams {
  status?: string;
  channel?: string;
  page?: number;
}

// ── Token helpers ──────────────────────────────────────────────

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ── Fetch wrapper ──────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    clearToken();
    window.location.href = '/login';
    throw new Error('Sesión expirada');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message = body.detail || `Error ${res.status}`;
    throw new Error(message);
  }

  return res.json();
}

// ── Auth service ───────────────────────────────────────────────

export const auth = {
  login(data: LoginRequest): Promise<AuthResponse> {
    return request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  register(data: RegisterRequest): Promise<AuthResponse> {
    return request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  me(): Promise<User> {
    return request<User>('/auth/me');
  },

  refresh(): Promise<AuthResponse> {
    return request<AuthResponse>('/auth/refresh', {
      method: 'POST',
    });
  },

  sendMagicLink(email: string): Promise<{ message: string }> {
    return request<{ message: string }>('/auth/magic-link', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  },

  verifyMagicLink(token: string): Promise<AuthResponse> {
    return request<AuthResponse>(`/auth/verify?token=${encodeURIComponent(token)}`);
  },
};

// ── Dashboard service ──────────────────────────────────────────

export const dashboard = {
  stats(): Promise<DashboardStats> {
    return request<DashboardStats>('/dashboard/stats');
  },
};

// ── Appointment service ────────────────────────────────────────

export const appointments = {
  list(params?: AppointmentListParams): Promise<Appointment[]> {
    const qs = new URLSearchParams();
    if (params?.date) qs.set('date', params.date);
    if (params?.doctor_id) qs.set('doctor_id', params.doctor_id);
    if (params?.status) qs.set('status', params.status);
    const query = qs.toString();
    return request<Appointment[]>(`/appointments${query ? `?${query}` : ''}`);
  },

  get(id: string): Promise<Appointment> {
    return request<Appointment>(`/appointments/${id}`);
  },

  cancel(id: string): Promise<Appointment> {
    return request<Appointment>(`/appointments/${id}/cancel`, { method: 'POST' });
  },

  confirm(id: string): Promise<Appointment> {
    return request<Appointment>(`/appointments/${id}/confirm`, { method: 'POST' });
  },

  markAttended(id: string): Promise<Appointment> {
    return request<Appointment>(`/appointments/${id}/mark-attended`, { method: 'POST' });
  },

  async exportCsv(params?: { date?: string }): Promise<Blob> {
    const qs = new URLSearchParams();
    if (params?.date) qs.set('date', params.date);
    const query = qs.toString();
    const path = `/appointments/export${query ? `?${query}` : ''}`;

    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(`${BASE_URL}${path}`, { headers });
    if (!res.ok) throw new Error('Error al exportar CSV');
    return res.blob();
  },
};

// ── Conversation service ───────────────────────────────────────

export const conversations = {
  list(params?: ConversationListParams): Promise<Conversation[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.channel) qs.set('channel', params.channel);
    if (params?.page) qs.set('page', String(params.page));
    const query = qs.toString();
    return request<Conversation[]>(`/conversations${query ? `?${query}` : ''}`);
  },

  get(id: string): Promise<ConversationDetail> {
    return request<ConversationDetail>(`/conversations/${id}`);
  },

  take(id: string): Promise<ConversationDetail> {
    return request<ConversationDetail>(`/conversations/${id}/take`, { method: 'POST' });
  },

  reply(id: string, message: string): Promise<ConversationMessage> {
    return request<ConversationMessage>(`/conversations/${id}/reply`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  },

  returnToBot(id: string): Promise<ConversationDetail> {
    return request<ConversationDetail>(`/conversations/${id}/return-to-bot`, { method: 'POST' });
  },
};

// ── Clinic Config types & service ──────────────────────────────

export interface DayHours {
  start: string;
  end: string;
  closed?: boolean;
}

export interface ClinicConfig {
  name: string;
  address: string;
  phone: string;
  email: string;
  business_hours: Record<string, DayHours>;
  appointment_duration_minutes: number;
  prices: { particular: number; obras_sociales: number };
  welcome_message: string;
}

export const clinicConfig = {
  get(): Promise<ClinicConfig> {
    return request<ClinicConfig>('/clinic-config');
  },

  update(data: Partial<ClinicConfig>): Promise<ClinicConfig> {
    return request<ClinicConfig>('/clinic-config', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },
};

// ── Doctor types & service ─────────────────────────────────────

export interface Doctor {
  id: string;
  name: string;
  specialty: string;
  calendar_id?: string;
  is_active: boolean;
  created_at?: string;
}

export interface DoctorInput {
  name: string;
  specialty: string;
  calendar_id?: string;
}

export const doctors = {
  list(): Promise<Doctor[]> {
    return request<Doctor[]>('/doctors');
  },

  create(data: DoctorInput): Promise<Doctor> {
    return request<Doctor>('/doctors', { method: 'POST', body: JSON.stringify(data) });
  },

  update(id: string, data: Partial<DoctorInput>): Promise<Doctor> {
    return request<Doctor>(`/doctors/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  },

  remove(id: string): Promise<void> {
    return request<void>(`/doctors/${id}`, { method: 'DELETE' });
  },
};

// ── FAQ types & service ────────────────────────────────────────

export interface FAQ {
  id: string;
  question: string;
  answer: string;
  category: string;
  is_active: boolean;
  sort_order?: number;
  created_at?: string;
}

export interface FAQInput {
  question: string;
  answer: string;
  category: string;
}

export const faqs = {
  list(search?: string): Promise<FAQ[]> {
    const qs = search ? `?search=${encodeURIComponent(search)}` : '';
    return request<FAQ[]>(`/faqs${qs}`);
  },

  create(data: FAQInput): Promise<FAQ> {
    return request<FAQ>('/faqs', { method: 'POST', body: JSON.stringify(data) });
  },

  update(id: string, data: Partial<FAQInput>): Promise<FAQ> {
    return request<FAQ>(`/faqs/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  },

  remove(id: string): Promise<void> {
    return request<void>(`/faqs/${id}`, { method: 'DELETE' });
  },
};

// ── Team / User types & service ────────────────────────────────

export interface TeamMember {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'recepcionista';
  is_active: boolean;
  last_login?: string;
  created_at?: string;
}

export interface InviteInput {
  email: string;
  role: 'admin' | 'recepcionista';
}

export const team = {
  list(): Promise<TeamMember[]> {
    return request<TeamMember[]>('/users');
  },

  invite(data: InviteInput): Promise<{ message: string }> {
    return request<{ message: string }>('/users/invite', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  remove(id: string): Promise<void> {
    return request<void>(`/users/${id}`, { method: 'DELETE' });
  },
};

// ── Calendar types & service ───────────────────────────────────

export interface CalendarStatus {
  connected: boolean;
  email?: string;
  calendar_name?: string;
}

export interface AuthUrlResponse {
  url: string;
}

export const calendar = {
  getAuthUrl(): Promise<AuthUrlResponse> {
    return request<AuthUrlResponse>('/calendar/auth-url');
  },

  handleCallback(code: string): Promise<{ message: string }> {
    return request<{ message: string }>('/calendar/callback', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  },

  status(): Promise<CalendarStatus> {
    return request<CalendarStatus>('/calendar/status');
  },

  disconnect(): Promise<{ message: string }> {
    return request<{ message: string }>('/calendar/disconnect', { method: 'DELETE' });
  },
};

// ── Onboarding types & service ─────────────────────────────────

export interface OnboardingStep {
  id: number;
  name: string;
  completed: boolean;
}

export interface OnboardingStatus {
  completed: boolean;
  current_step: number;
  steps: OnboardingStep[];
}

export interface FAQTemplate {
  question: string;
  answer: string;
  category: string;
}

export interface FAQTemplatesResponse {
  templates: FAQTemplate[];
}

export const onboarding = {
  status(): Promise<OnboardingStatus> {
    return request<OnboardingStatus>('/onboarding/status');
  },

  markStep(stepId: number): Promise<OnboardingStatus> {
    return request<OnboardingStatus>('/onboarding/step', {
      method: 'PUT',
      body: JSON.stringify({ step_id: stepId }),
    });
  },

  faqTemplates(): Promise<FAQTemplatesResponse> {
    return request<FAQTemplatesResponse>('/onboarding/faq-templates');
  },
};

// ── Billing types & service ────────────────────────────────────

export interface BillingStatus {
  plan: string;
  status: string;
  trial_ends_at: string | null;
  days_remaining: number | null;
  mp_preference_id: string | null;
}

export interface CheckoutResponse {
  preference_id: string;
  init_point: string;
}

export const billing = {
  status(): Promise<BillingStatus> {
    return request<BillingStatus>('/billing/status');
  },

  checkout(): Promise<CheckoutResponse> {
    return request<CheckoutResponse>('/billing/checkout', { method: 'POST' });
  },

  cancel(): Promise<{ status: string }> {
    return request<{ status: string }>('/billing/cancel', { method: 'POST' });
  },
};

// ── Admin types & service ──────────────────────────────────────

export interface TenantAdmin {
  id: string;
  name: string;
  slug: string;
  email: string;
  plan: string;
  status: string;
  trial_ends_at: string | null;
  created_at: string;
}

export interface AdminTenantsParams {
  status?: string;
  plan?: string;
}

export const admin = {
  tenants(params?: AdminTenantsParams): Promise<TenantAdmin[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.plan) qs.set('plan', params.plan);
    const query = qs.toString();
    return request<TenantAdmin[]>(`/admin/tenants${query ? `?${query}` : ''}`);
  },

  suspend(id: string): Promise<{ status: string }> {
    return request<{ status: string }>(`/admin/tenants/${id}/suspend`, { method: 'POST' });
  },

  activate(id: string): Promise<{ status: string; trial_ends_at?: string }> {
    return request<{ status: string; trial_ends_at?: string }>(`/admin/tenants/${id}/activate`, { method: 'POST' });
  },

  markPaid(id: string): Promise<{ plan: string; status: string; message: string }> {
    return request<{ plan: string; status: string; message: string }>(`/admin/tenants/${id}/mark-paid`, { method: 'POST' });
  },
};
