# Diseño Técnico — Chatbot SaaS para Clínicas de Medicina General

**Cambio**: chatbot-clinica-mvp
**Fase**: Design
**Depende de**: spec.md
**Fecha**: 2026-06-04

---

## 1. Arquitectura General

### Diagrama de Contexto

```
┌────────────────────────────────────────────────────────────┐
│                    INTERNET                                 │
└────────────────────────────────────────────────────────────┘
         │                            │
         ▼                            ▼
┌──────────────────┐      ┌──────────────────────┐
│   Paciente       │      │  Administrador       │
│  (WhatsApp App)  │      │  (Browser Web)       │
└────────┬─────────┘      └──────────┬───────────┘
         │                           │
         ▼                           ▼
┌──────────────────┐      ┌──────────────────────┐
│  Evolution API   │      │  React SPA           │
│  (WhatsApp       │      │  (Panel Admin)       │
│   Gateway)       │      │                      │
└────────┬─────────┘      └──────────┬───────────┘
         │                           │
         │    Webhook POST           │    REST API
         ▼                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   FastAPI Server                              │
│                                                               │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  ┌───────────┐  │
│  │WhatsApp │  │  Intent   │  │  Actions   │  │   Admin   │  │
│  │Webhook  │──▶│Classifier│──▶│(Agendar,  │──▶│   API     │  │
│  │ Router  │  │ (LLM)    │  │ Cancelar,  │  │  Router   │  │
│  └─────────┘  └──────────┘  │ FAQ, etc)  │  └───────────┘  │
│                             └────────────┘                  │
│                                   │                          │
│                          ┌────────┴─────────┐               │
│                          │  External APIs   │               │
│                          │  - Google Cal    │               │
│                          │  - OpenAI        │               │
│                          │  - Evolution API │               │
│                          └──────────────────┘               │
│                                   │                          │
│                          ┌────────┴─────────┐               │
│                          │   PostgreSQL     │               │
│                          │   (SQLAlchemy)   │               │
│                          └──────────────────┘               │
└──────────────────────────────────────────────────────────────┘
```

### Patrón Arquitectónico: **Hexagonal (Ports & Adapters) + Capas**

```
┌─────────────────────────────────────────┐
│              Presentation               │
│  (Webhooks, REST API, React SPA)        │
├─────────────────────────────────────────┤
│              Application                │
│  (Orquestador, Use Cases)               │
├─────────────────────────────────────────┤
│              Domain                     │
│  (Entidades, Reglas de Negocio)         │
├─────────────────────────────────────────┤
│              Infrastructure             │
│  (PostgreSQL, OpenAI, Google, Evolution)│
└─────────────────────────────────────────┘
```

**Razonamiento**: Hexagonal permite cambiar cualquier adaptador externo (ej: Evolution API por Twilio, Google Calendar por Outlook) sin tocar la lógica de negocio. Es la arquitectura correcta para un SaaS que puede evolucionar.

---

## 2. Stack Tecnológico Detallado

| Capa | Tecnología | Versión | Razón |
|---|---|---|---|
| Backend | **FastAPI** | 0.115+ | Async nativo, rendimiento, autodoc |
| Runtime | **Python** | 3.12+ | Última versión estable con mejoras de perf |
| ORM | **SQLAlchemy** | 2.0+ | Async soportado, maduro, flexible |
| Migraciones | **Alembic** | 1.13+ | Estándar de facto con SQLAlchemy |
| DB | **PostgreSQL** | 16+ | Multi-tenant, JSONB, robustez |
| Cache | **Redis** | 7+ | Sesiones, rate limiting, cola de tareas |
| LLM | **OpenAI GPT-4o-mini** | API | Mejor relación costo/calidad |
| WhatsApp | **Evolution API** | v2+ | Self-hosted, gratis, control total |
| Calendar | **Google Calendar API** | v3 | Más usado en clínicas |
| Auth | **JWT + python-jose** | — | Simple, stateless |
| Frontend | **React + Vite** | 18+ / 6+ | Panel SPA rápido |
| UI | **Tailwind CSS** | 4+ | Productivo, sin fricción |
| HTTP | **httpx** | — | Async HTTP client |
| Background | **Celery** | — | Tareas programadas (recordatorios) |
| Broker | **Redis** | — | Backend de Celery |
| Container | **Docker** | — | Entorno reproducible |
| Hosting | **Railway / Render** | — | Simple para startups |

---

## 3. Estructura del Proyecto

```
chatbot-clinica/
├── backend/
│   ├── alembic/                  # Migraciones de DB
│   │   ├── versions/
│   │   ├── env.py
│   │   └── alembic.ini
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app, startup
│   │   ├── config.py             # Settings (pydantic-settings)
│   │   ├── dependencies.py       # FastAPI dependencies (DB, tenant)
│   │   │
│   │   ├── domain/               # Capa de dominio (pura, sin dependencias externas)
│   │   │   ├── __init__.py
│   │   │   ├── models/           # Entidades de dominio
│   │   │   │   ├── tenant.py
│   │   │   │   ├── patient.py
│   │   │   │   ├── appointment.py
│   │   │   │   ├── conversation.py
│   │   │   │   ├── clinic_config.py
│   │   │   │   └── user.py
│   │   │   ├── enums.py          # Enums compartidos
│   │   │   └── interfaces/       # Interfaces (puertos)
│   │   │       ├── calendar.py
│   │   │       ├── messaging.py
│   │   │       └── llm.py
│   │   │
│   │   ├── application/          # Casos de uso
│   │   │   ├── __init__.py
│   │   │   ├── appointment/
│   │   │   │   ├── book.py
│   │   │   │   ├── cancel.py
│   │   │   │   ├── reschedule.py
│   │   │   │   └── get_slots.py
│   │   │   ├── conversation/
│   │   │   │   ├── classify_intent.py
│   │   │   │   ├── handle_message.py
│   │   │   │   └── escalate.py
│   │   │   ├── faq/
│   │   │   │   ├── answer.py
│   │   │   │   └── manage.py
│   │   │   └── reminder/
│   │   │       └── send.py
│   │   │
│   │   ├── infrastructure/       # Implementaciones concretas
│   │   │   ├── __init__.py
│   │   │   ├── database/         # SQLAlchemy models + repo
│   │   │   │   ├── models/       # Modelos ORM
│   │   │   │   │   ├── tenant.py
│   │   │   │   │   ├── patient.py
│   │   │   │   │   ├── appointment.py
│   │   │   │   │   ├── conversation.py
│   │   │   │   │   ├── clinic_config.py
│   │   │   │   │   └── user.py
│   │   │   │   ├── repository/   # Implementación repositorios
│   │   │   │   │   ├── tenant_repo.py
│   │   │   │   │   ├── patient_repo.py
│   │   │   │   │   ├── appointment_repo.py
│   │   │   │   │   └── conversation_repo.py
│   │   │   │   └── session.py    # Async session management
│   │   │   │
│   │   │   ├── whatsapp/         # Adaptador WhatsApp
│   │   │   │   ├── evolution.py  # Evolution API client
│   │   │   │   └── models.py     # DTOs de WhatsApp
│   │   │   │
│   │   │   ├── calendar/         # Adaptador Google Calendar
│   │   │   │   ├── google.py     # Google Calendar client
│   │   │   │   └── models.py     # DTOs de calendario
│   │   │   │
│   │   │   ├── llm/              # Adaptador IA
│   │   │   │   ├── openai_client.py
│   │   │   │   ├── intent_classifier.py
│   │   │   │   └── prompts.py    # Prompts para GPT
│   │   │   │
│   │   │   └── auth/             # Autenticación
│   │   │       ├── jwt.py
│   │   │       └── password.py
│   │   │
│   │   └── presentation/         # Capa de presentación
│   │       ├── __init__.py
│   │       ├── webhooks/         # Endpoints para WhatsApp
│   │       │   ├── evolution.py
│   │       │   └── schemas.py
│   │       ├── api/              # REST API para el panel
│   │       │   ├── v1/
│   │       │   │   ├── appointments.py
│   │       │   │   ├── conversations.py
│   │       │   │   ├── clinic_config.py
│   │       │   │   ├── auth.py
│   │       │   │   ├── users.py
│   │       │   │   └── webhooks.py
│   │       │   └── deps.py
│   │       └── middleware/
│   │           ├── tenant.py     # Middleware de tenant
│   │           └── auth.py       # Middleware de autenticación
│   │
│   ├── tasks/                    # Tareas Celery (background)
│   │   ├── __init__.py
│   │   ├── celery_app.py
│   │   ├── reminders.py          # Recordatorios programados
│   │   └── cleanup.py            # Limpieza de datos
│   │
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── conftest.py
│   │
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── dev.txt
│   │   └── prod.txt
│   │
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/             # API client
│   │   ├── contexts/
│   │   └── App.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 4. Modelo de Base de Datos

### Diagrama Entidad-Relación (textual)

```
tenants ──1:N──> users
tenants ──1:N──> clinic_configs
tenants ──1:N──> doctors
tenants ──1:N──> appointments
tenants ──1:N──> conversations
tenants ──1:N──> conversation_messages

patients ──1:N──> appointments
patients ──1:N──> conversations

doctors ──1:N──> appointments
doctors ──1──> google_calendar_tokens

appointments ──1:1──> google_calendar_events
```

### Tablas

```sql
-- ============================================
-- TENANTS (Multi-tenencia)
-- ============================================
CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,          -- Nombre de la clínica
    slug            VARCHAR(100) UNIQUE NOT NULL,   -- Identificador URL
    phone_number    VARCHAR(20) UNIQUE NOT NULL,    -- Número WhatsApp
    status          VARCHAR(20) DEFAULT 'active',    -- active, suspended, cancelled
    plan            VARCHAR(50) DEFAULT 'basic',     -- basic, professional, premium
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- USERS (Admin, Recepcionista)
-- ============================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255),
    name            VARCHAR(255) NOT NULL,
    role            VARCHAR(50) NOT NULL DEFAULT 'recepcionista',  -- admin, recepcionista
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, email)
);

-- ============================================
-- CLINIC_CONFIG (Configuración de la clínica)
-- ============================================
CREATE TABLE clinic_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    address         TEXT,
    city            VARCHAR(100),
    phone           VARCHAR(20),
    email_contact   VARCHAR(255),
    business_hours  JSONB NOT NULL DEFAULT '{}',     -- { "monday": {"start": "08:00", "end": "17:00"}, ... }
    appointment_duration_minutes INT DEFAULT 20,
    welcome_message TEXT DEFAULT '¡Hola! Soy el asistente virtual de {clinic_name}. ¿En qué puedo ayudarte?',
    emergency_phone VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- FAQS (Base de conocimiento)
-- ============================================
CREATE TABLE faqs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    category        VARCHAR(100) DEFAULT 'general',  -- horarios, precios, preparacion, etc.
    is_active       BOOLEAN DEFAULT TRUE,
    sort_order      INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- DOCTORS (Médicos de la clínica)
-- ============================================
CREATE TABLE doctors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    specialty       VARCHAR(255) DEFAULT 'Medicina General',
    email           VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- GOOGLE_CALENDAR_TOKENS (OAuth tokens)
-- ============================================
CREATE TABLE google_calendar_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    doctor_id       UUID REFERENCES doctors(id) ON DELETE CASCADE,
    calendar_id     VARCHAR(255) NOT NULL,
    access_token    TEXT,                              -- Encriptado
    refresh_token   TEXT,                              -- Encriptado
    token_expiry    TIMESTAMPTZ,
    calendar_email  VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- PATIENTS
-- ============================================
CREATE TABLE patients (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    phone_number    VARCHAR(20) NOT NULL,
    name            VARCHAR(255),
    email           VARCHAR(255),
    notes           TEXT,
    reminders_opt_in BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, phone_number)
);

-- ============================================
-- APPOINTMENTS (Turnos)
-- ============================================
CREATE TYPE appointment_status AS ENUM (
    'pending', 'confirmed', 'cancelled_by_patient', 'cancelled_by_clinic',
    'rescheduled', 'unconfirmed', 'attended', 'no_show'
);

CREATE TABLE appointments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    patient_id          UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id           UUID REFERENCES doctors(id) ON DELETE SET NULL,
    google_event_id     VARCHAR(255),                  -- ID del evento en Google Calendar
    status              appointment_status DEFAULT 'confirmed',
    start_time          TIMESTAMPTZ NOT NULL,
    end_time            TIMESTAMPTZ NOT NULL,
    reason              TEXT,                           -- Motivo de consulta
    reminder_1_sent     BOOLEAN DEFAULT FALSE,
    reminder_2_sent     BOOLEAN DEFAULT FALSE,
    reminder_confirmed  BOOLEAN DEFAULT FALSE,
    cancelled_at        TIMESTAMPTZ,
    cancellation_reason VARCHAR(50),                    -- patient_request, no_show, clinic
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_time_range CHECK (end_time > start_time)
);

CREATE INDEX idx_appointments_tenant_date ON appointments(tenant_id, start_time);
CREATE INDEX idx_appointments_patient ON appointments(patient_id, status);
CREATE INDEX idx_appointments_reminder ON appointments(tenant_id, status, start_time)
    WHERE status = 'confirmed' AND reminder_1_sent = FALSE;

-- ============================================
-- CONVERSATIONS (Sesiones de chat)
-- ============================================
CREATE TYPE conversation_status AS ENUM (
    'active', 'escalated', 'resolved', 'archived'
);

CREATE TYPE conversation_channel AS ENUM (
    'whatsapp', 'web'
);

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    patient_id      UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    status          conversation_status DEFAULT 'active',
    channel         conversation_channel DEFAULT 'whatsapp',
    escalated_at    TIMESTAMPTZ,
    escalated_to    UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- CONVERSATION_MESSAGES
-- ============================================
CREATE TYPE message_origin AS ENUM ('patient', 'bot', 'human');

CREATE TABLE conversation_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    origin          message_origin NOT NULL,
    content         TEXT NOT NULL,
    intent          VARCHAR(50),                       -- agendar, cancelar, faq, etc.
    metadata        JSONB DEFAULT '{}',                -- datos adicionales (confianza, latencia, etc.)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON conversation_messages(conversation_id, created_at);

-- ============================================
-- TENANT_SETTINGS (Configuración general)
-- ============================================
CREATE TABLE tenant_settings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    reminder_1_hours_before INT DEFAULT 24,
    reminder_2_hours_before INT DEFAULT 6,
    max_days_in_advance INT DEFAULT 60,
    min_hours_before_booking INT DEFAULT 1,
    min_hours_before_cancel INT DEFAULT 2,
    no_reminder_hour_start INT DEFAULT 22,              -- No enviar recordatorios entre 22:00
    no_reminder_hour_end INT DEFAULT 8,                 -- y 8:00
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- AUDIT_LOG (Auditoría)
-- ============================================
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(100) NOT NULL,              -- appointment.created, appointment.cancelled, etc.
    entity_type     VARCHAR(50) NOT NULL,               -- appointment, patient, config
    entity_id       UUID,
    details         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, created_at);
```

---

## 5. API Endpoints

### Webhooks (WhatsApp)

| Método | Path | Propósito |
|---|---|---|
| POST | `/api/v1/webhooks/whatsapp/evolution` | Recibe mensajes de Evolution API |
| GET | `/api/v1/webhooks/whatsapp/evolution/status` | Health check del webhook |

### Autenticación

| Método | Path | Propósito |
|---|---|---|
| POST | `/api/v1/auth/register` | Registrar nueva clínica (onboarding) |
| POST | `/api/v1/auth/login` | Login email + password → JWT |
| POST | `/api/v1/auth/magic-link` | Enviar magic link por email |
| GET | `/api/v1/auth/verify` | Verificar magic link |
| POST | `/api/v1/auth/refresh` | Refrescar JWT |

### Admin API (protegida por JWT + tenant)

| Método | Path | Propósito |
|---|---|---|
| **Dashboard** | | |
| GET | `/api/v1/dashboard/stats` | Estadísticas del dashboard |
| **Turnos** | | |
| GET | `/api/v1/appointments` | Listar turnos (filtros: fecha, doctor, estado) |
| GET | `/api/v1/appointments/{id}` | Detalle de turno |
| POST | `/api/v1/appointments` | Crear turno manualmente |
| PATCH | `/api/v1/appointments/{id}/cancel` | Cancelar turno |
| PATCH | `/api/v1/appointments/{id}/complete` | Marcar como atendido |
| GET | `/api/v1/appointments/export` | Exportar CSV |
| **Conversaciones** | | |
| GET | `/api/v1/conversations` | Listar conversaciones |
| GET | `/api/v1/conversations/{id}` | Historial de mensajes |
| POST | `/api/v1/conversations/{id}/take` | Tomar conversación (reclamo) |
| POST | `/api/v1/conversations/{id}/reply` | Responder como humano |
| POST | `/api/v1/conversations/{id}/return-to-bot` | Devolver control al bot |
| **Configuración** | | |
| GET | `/api/v1/clinic` | Obtener configuración |
| PUT | `/api/v1/clinic` | Actualizar configuración |
| GET | `/api/v1/faqs` | Listar FAQs |
| POST | `/api/v1/faqs` | Crear FAQ |
| PUT | `/api/v1/faqs/{id}` | Editar FAQ |
| DELETE | `/api/v1/faqs/{id}` | Eliminar FAQ |
| GET | `/api/v1/doctors` | Listar médicos |
| POST | `/api/v1/doctors` | Crear médico |
| PUT | `/api/v1/doctors/{id}` | Editar médico |
| **Google Calendar** | | |
| GET | `/api/v1/calendar/auth-url` | Obtener URL de OAuth |
| POST | `/api/v1/calendar/callback` | Procesar callback OAuth |
| GET | `/api/v1/calendar/status` | Estado de conexión |
| DELETE | `/api/v1/calendar/disconnect` | Desconectar calendario |
| **Usuarios** | | |
| GET | `/api/v1/users` | Listar miembros del equipo |
| POST | `/api/v1/users/invite` | Invitar miembro |
| DELETE | `/api/v1/users/{id}` | Remover miembro |

---

## 6. Flujo Detallado del Orquestador de IA

Este es el corazón del sistema. Cuando llega un mensaje de WhatsApp:

```
1. RECIBIR MENSAJE
   Evolution API → Webhook POST → FastAPI

2. IDENTIFICAR TENANT
   Buscar tenant por número destino
   └─ Si no existe → responder "número no registrado" y loguear

3. IDENTIFICAR/CREAR PACIENTE
   Buscar paciente por número origen + tenant
   └─ Si no existe → crear nuevo paciente

4. OBTENER/CREAR CONVERSACIÓN ACTIVA
   Buscar conversación con status = active para ese paciente
   └─ Si no existe → crear nueva conversación

5. CLASIFICAR INTENCIÓN
   Enviar mensaje a GPT-4o-mini con:
   - System prompt: rol del bot + info de la clínica
   - Historial de los últimos 5 mensajes
   - Instrucción: clasificar en una de las intenciones

   Response esperado: { "intent": "agendar", "confidence": 0.95, "params": {...} }

   └─ Si confidence < 0.7 → intent = "desconocido"

6. EJECUTAR ACCIÓN SEGÚN INTENCIÓN

   agendar        → F2 handler (check availability, offer slots, book)
   cancelar       → F3 handler (find appointment, confirm, cancel)
   reprogramar    → F3 handler (find appointment, offer new slots)
   consultar_turno → F3 handler (show upcoming appointments)
   faq            → F5 handler (search FAQ + GPT response)
   humano         → F6 handler (escalate to admin panel)
   saludo         → Responder mensaje de bienvenida
   desconocido    → Pedir clarificación, si 2º intento → derivar a humano

7. GUARDAR MENSAJE EN DB
   INSERT en conversation_messages

8. ENVIAR RESPUESTA
   Evolution API → Mensaje WhatsApp al paciente

9. SI APLICA → ACCIONES POST-RESPUESTA
   - Si se agendó turno → programar recordatorio en Celery
   - Si se derivó → notificar al panel (WebSocket)
```

### System Prompt del Bot

```
Sos el asistente virtual de {clinic_name}, una clínica de medicina general.

INFORMACIÓN DE LA CLÍNICA:
- Dirección: {address}
- Horarios: {business_hours}
- Teléfono: {phone}
- Precios: {prices}

REGLAS:
1. Respondé siempre en español, con tono amable y profesional.
2. No dés consejo médico bajo ninguna circunstancia.
3. Si el paciente menciona síntomas, dolor, o emergencias, derivá a humano.
4. Antes de agendar/cancelar/reprogramar, siempre confirmá con el paciente.
5. Si no entendés la intención, pedí que reformule amablemente.
6. Usá la información de FAQ de la clínica para responder preguntas.
7. Si te preguntan algo que no está en tu base de conocimiento, decí que no tenés esa información y ofrecé derivar a recepción.
8. Tu objetivo: resolver la consulta en la menor cantidad de intercambios posible.

Formato de respuesta:
{
  "intent": "nombre_intencion",
  "confidence": 0.0-1.0,
  "message": "mensaje para el paciente",
  "params": {} // datos extra según la intención
}
```

---

## 7. Configuración de Infraestructura

### Docker Compose

```yaml
services:
  # --- Base de datos ---
  postgres:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: chatbot_clinica
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  # --- Cache / Message broker ---
  redis:
    image: redis:7-alpine

  # --- FastAPI Backend ---
  backend:
    build: ./backend
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql+asyncpg://app:${DB_PASSWORD}@postgres/chatbot_clinica
      REDIS_URL: redis://redis:6379/0
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      EVOLUTION_API_URL: ${EVOLUTION_API_URL}
      EVOLUTION_API_KEY: ${EVOLUTION_API_KEY}
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
      JWT_SECRET: ${JWT_SECRET}

  # --- Worker de tareas programadas (recordatorios) ---
  celery-worker:
    build: ./backend
    command: celery -A tasks.celery_app worker --loglevel=info
    depends_on:
      - postgres
      - redis
    environment:
      <<: *backend-environment  # mismas env vars

  # --- Celery Beat (cron scheduler) ---
  celery-beat:
    build: ./backend
    command: celery -A tasks.celery_app beat --loglevel=info
    depends_on:
      - redis
    environment:
      <<: *backend-environment

  # --- Evolution API (WhatsApp gateway) ---
  evolution-api:
    image: atendai/evolution-api:v2.0.0
    ports:
      - "8080:8080"
    volumes:
      - evolution-data:/evolution/instances
    environment:
      AUTHENTICATION_API_KEY: ${EVOLUTION_API_KEY}
      DATABASE_ENABLED: true
      DATABASE_CONNECTION_URI: postgresql://app:${DB_PASSWORD}@postgres/evolution
      # ... más config

  # --- Frontend ---
  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  pgdata:
  evolution-data:
```

### Variables de Entorno

```env
# App
APP_ENV=development
DEBUG=true
SECRET_KEY=change-me

# Database
DATABASE_URL=postgresql+asyncpg://app:password@localhost:5432/chatbot_clinica

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=sk-...

# WhatsApp (Evolution API)
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=your-evolution-api-key

# Google Calendar
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/calendar/callback

# JWT
JWT_SECRET=change-me
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
```

---

## 8. Decisiones Técnicas Clave

### ¿Por qué FastAPI y no Django?

| Aspecto | FastAPI | Django |
|---|---|---|
| Async nativo | ✅ Desde el vamos | ⚠️ Parcial (4.0+) |
| Rendimiento | 2-3x más requests/seg | Más pesado |
| Complejidad inicial | Baja | Alta (mucho boilerplate) |
| Admin built-in | ❌ (hacemos React) | ✅ (pero no queremos) |
| API-first | ✅ Diseñado para APIs | ✅ Mejoró pero no es nativo |

Para un SaaS que es esencialmente una API + webhooks + React, FastAPI es la opción correcta. Django sería overkill.

### ¿Por qué Evolution API y no Twilio?

| Aspecto | Evolution API | Twilio WhatsApp |
|---|---|---|
| Costo | **Gratis** (self-hosted) | $0.005/msg + $15/mes por número |
| Control total | ✅ Self-hosted | ❌ Dependés de Twilio |
| Multi-instancia | ✅ | Limitado |
| Setup | Más trabajo inicial | Plug-and-play |

Costo de Twilio para 300 turnos/mes con recordatorios: ~$20-30/mes adicionales. Evolution API es gratis. La compensación vale la pena para un SaaS con margen ajustado.

### ¿Por qué JWT y no sesiones?

Para un SPA + API REST, JWT es stateless, no requiere session store, y simplifica la autenticación entre servicios. Sesiones requieren sticky sessions o Redis compartido.

### Encriptación de Tokens

Los tokens de Google Calendar (access + refresh) se encriptan con `cryptography.fernet` antes de guardarse en DB. La clave de encriptación está en las variables de entorno.

---

## 9. Seguridad

### Datos de Pacientes
- Números de teléfono: se almacenan en claro (necesarios para WhatsApp), pero con acceso restringido
- Conversaciones: soft-delete después de 90 días
- Consentimiento: registrado en DB en el primer mensaje (timestamp + mensaje de aceptación)

### OWASP Top 10
- ✅ SQL Injection: SQLAlchemy parameterized queries
- ✅ XSS: React escapa output por defecto
- ✅ CSRF: JWT en headers (no cookies)
- ✅ Rate limiting: Redis + slowapi en endpoints críticos
- ✅ HTTPS: Enforced en producción
- ✅ Auth: JWT con expiración, refresh tokens

### Multi-tenencia
- Toda query incluye `WHERE tenant_id = ...`
- El middleware de tenant inyecta el tenant_id automáticamente
- Nunca se confía del cliente: el tenant_id se extrae del JWT (admin) o del webhook (paciente)

---

## 10. Próximos Pasos (para Tasks)

El diseño está listo para descomponerse en tareas de implementación:

1. **Setup del proyecto** — Docker, FastAPI skeleton, DB, migrations
2. **Modelos de datos** — SQLAlchemy models + Alembic migrations
3. **Autenticación** — Register, login, JWT, roles
4. **Gestión de tenants** — Middleware, CRUD
5. **Google Calendar** — OAuth, disponibilidad, eventos
6. **WhatsApp (Evolution API)** — Webhook, envío de mensajes
7. **Orquestador de IA** — Clasificador, intent handlers
8. **Agendar turnos** — F2 completo
9. **Cancelar / Reprogramar** — F3
10. **Recordatorios** — Celery tasks + templates WhatsApp
11. **FAQ** — CRUD + RAG con GPT
12. **Derivación a humano** — F6
13. **Panel web (React)** — Todas las secciones
14. **Onboarding** — Flujo de registro y configuración
15. **Testing** — Unit + integration

---

*Próximo paso: Descomponer en tareas de implementación (tasks)*
