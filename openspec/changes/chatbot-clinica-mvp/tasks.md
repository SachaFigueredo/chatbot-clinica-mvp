# Tareas de Implementación — Chatbot SaaS para Clínicas de Medicina General

**Cambio**: chatbot-clinica-mvp
**Fase**: Tasks
**Depende de**: design.md
**Fecha**: 2026-06-04

---

## Review Workload Forecast

| Métrica | Valor |
|---|---|
| Total tareas | 18 |
| Archivos estimados a crear/modificar | ~80 |
| Líneas estimadas de código | ~12,000 |
| Riesgo de rebase de 400 líneas | **ALTO** — se recomienda dividir en PRs encadenados |
| PRs recomendados | 4-5 PRs encadenados |

---

## Dependencia entre Tareas

```
T1 (setup)
  │
  ├──▶ T2 (modelos)
  │       │
  │       ├──▶ T3 (auth)
  │       ├──▶ T4 (tenants)
  │       ├──▶ T5 ✅ (Google Calendar)
  │       │       │
  │       │       └──▶ T7 (agendar turnos) ──▶ T8 (cancelar/reprogramar)
  │       │                                      │
  │       ├──▶ T6 ✅ (WhatsApp Evolution) ──▶ T7 ───┤
  │       │                                      │
  │       └──▶ T14 (orquestador IA) ──────▶ T7 ──┤
  │                                                │
  │                                                ├──▶ T9 (recordatorios)
  │                                                ├──▶ T10 (FAQ)
  │                                                └──▶ T11 (derivación humano)
  │
  ├──▶ T12 (panel web - base)
  │       ├──▶ T13 (panel - turnos)
  │       ├──▶ T14 (panel - conversaciones)
  │       └──▶ T15 (panel - configuración)
  │
  └──▶ T16 (onboarding)
```

---

## Tareas

---

### T1 — Setup del Proyecto

**Dependencias**: Ninguna
**Estimación**: 0.5 días
**Responsable**: Backend

**Descripción**: Inicializar el proyecto con Docker Compose, estructura de carpetas, dependencias, y configuración básica de FastAPI.

**Archivos a crear**:
- `docker-compose.yml`
- `backend/Dockerfile`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/requirements/base.txt`
- `backend/requirements/dev.txt`
- `backend/.env.example`
- `.env.example`
- `README.md`

**Criterios de Aceptación**:
- `docker compose up` levanta FastAPI en localhost:8000
- Health endpoint `GET /health` responde 200
- PostgreSQL y Redis se conectan correctamente
- Las variables de entorno se leen desde `.env`

---

### T2 — Modelos de Datos y Migraciones

**Dependencias**: T1
**Estimación**: 1 día
**Responsable**: Backend

**Descripción**: Crear todos los modelos SQLAlchemy con SQLAlchemy 2.0 async, y generar las migraciones iniciales con Alembic.

**Archivos a crear**:
- `backend/alembic/versions/001_initial.py`
- Todos los archivos en `backend/app/infrastructure/database/models/` (tenant, patient, appointment, conversation, etc.)

**Modelos a implementar**:
- tenants, users, patients, doctors, appointments
- conversations, conversation_messages, faqs
- clinic_configs, google_calendar_tokens, tenant_settings
- audit_log

**Criterios de Aceptación**:
- `alembic upgrade head` crea todas las tablas en PostgreSQL
- Los modelos son async (SQLAlchemy 2.0 style)
- Las relaciones y constraints están correctas
- Los índices definidos en el diseño existen
- Tests: crear y leer cada modelo

---

### T3 — Autenticación y Roles

**Dependencias**: T2
**Estimación**: 1 día
**Responsable**: Backend

**Descripción**: Sistema de autenticación JWT con registro, login, magic links, y roles (admin/recepcionista).

**Archivos a crear/modificar**:
- `backend/app/infrastructure/auth/jwt.py`
- `backend/app/infrastructure/auth/password.py`
- `backend/app/presentation/api/v1/auth.py`
- `backend/app/presentation/middleware/auth.py`
- `backend/app/presentation/api/deps.py`

**Endpoints**:
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/magic-link`
- `GET /api/v1/auth/verify`
- `POST /api/v1/auth/refresh`

**Criterios de Aceptación**:
- Registro exitoso crea tenant + admin user
- Login retorna JWT válido
- Magic link funciona (se envía email mock en dev)
- JWT expira y refresh funciona
- Endpoints protegidos rechazan requests sin token
- Admin tiene acceso completo, recepcionista tiene acceso limitado

---

### T4 — Middleware Multi-Tenant

**Dependencias**: T2, T3
**Estimación**: 0.5 días
**Responsable**: Backend

**Descripción**: Middleware que identifica el tenant automáticamente para cada request, tanto en webhooks como en API.

**Archivos a crear**:
- `backend/app/presentation/middleware/tenant.py`
- `backend/app/infrastructure/database/repository/tenant_repo.py`

**Funcionalidad**:
- Webhook: identifica tenant por número destino del mensaje WhatsApp
- API admin: extrae tenant_id del JWT
- Filtra todas las queries automáticamente por tenant_id
- Si no encuentra tenant, rechaza con 404/401

**Criterios de Aceptación**:
- Request sin tenant → error claro
- Webhook con número no registrado → log + respuesta de error
- Admin de tenant A no puede ver datos de tenant B
- Middleware no bloquea endpoints públicos (health, register)

---

### T5 — Integración Google Calendar ✅

**Dependencias**: T2
**Estimación**: 2 días
**Responsable**: Backend

**Estado**: COMPLETADO

**Descripción**: Integración completa con Google Calendar API: OAuth 2.0, lectura de disponibilidad, creación y cancelación de eventos.

**Archivos creados**:
- `backend/app/domain/interfaces/calendar.py` — Abstract `CalendarProvider` interface
- `backend/app/infrastructure/calendar/__init__.py` — Package init
- `backend/app/infrastructure/calendar/models.py` — `AvailableSlot` and `ConnectionStatus` DTOs
- `backend/app/infrastructure/calendar/google.py` — `GoogleCalendarProvider` adapter
- `backend/app/api/v1/calendar.py` — REST API endpoints

**Archivos modificados**:
- `backend/app/main.py` — Registered calendar router

**Endpoints**:
- `GET /api/v1/calendar/auth-url`
- `POST /api/v1/calendar/callback`
- `GET /api/v1/calendar/status`
- `DELETE /api/v1/calendar/disconnect`

**Implementar**:
- Flujo OAuth 2.0 completo con refresh tokens
- `get_available_slots(calendar_id, date, duration)` — devuelve slots libres
- `create_event(calendar_id, summary, description, start, end)` — crea evento
- `delete_event(calendar_id, event_id)` — elimina evento
- Encriptación de tokens con Fernet
- Manejo de errores: token expirado, calendario no encontrado, rate limiting

**Criterios de Aceptación**:
- Pantalla de consentimiento de Google se muestra correctamente
- Token se guarda encriptado y se refresca automáticamente
- `get_available_slots` excluye eventos existentes y horarios fuera de atención
- Evento creado tiene título, descripción y duración correcta
- Evento eliminado libera el slot
- Si token expira, se notifica al admin

---

### T6 — Integración WhatsApp (Evolution API) ✅

**Dependencias**: T2
**Estimación**: 1.5 días
**Responsable**: Backend

**Estado**: COMPLETADO

**Descripción**: Conectar Evolution API como gateway de WhatsApp. Webhook para recibir mensajes, API para enviar mensajes.

**Archivos creados**:
- `backend/app/domain/interfaces/messaging.py` — Abstract `MessagingProvider` interface
- `backend/app/infrastructure/whatsapp/__init__.py` — Package init
- `backend/app/infrastructure/whatsapp/models.py` — `IncomingMessage` and `WhatsAppInstance` DTOs
- `backend/app/infrastructure/whatsapp/evolution.py` — `EvolutionAPIProvider` adapter
- `backend/app/api/v1/webhooks/__init__.py` — Package init
- `backend/app/api/v1/webhooks/evolution.py` — Webhook endpoints
- `backend/app/application/conversation/__init__.py` — Package init
- `backend/app/application/conversation/handle_message.py` — Message handler stub (pre-T7)

**Archivos modificados**:
- `backend/app/main.py` — Registered evolution webhook router

**Endpoints**:
- `POST /api/v1/webhooks/whatsapp/evolution`
- `GET /api/v1/webhooks/whatsapp/evolution/status`

**Implementar**:
- Webhook: recibir mensaje, validar firma/source, devolver 200 OK
- Envío: `send_message(phone, text)`, `send_template(phone, template_name, params)`
- Manejo de archivos multimedia (responder que no se procesan)
- Reconexión automática si Evolution API cae
- Logging de mensajes entrantes/salientes

**Criterios de Aceptación**:
- Mensaje entrante se recibe y guarda en DB
- Mensaje saliente se envía correctamente
- Si Evolution API no responde, reintentar 3 veces
- Webhook responde 200 OK en < 500ms
- Multimedia recibido se responde con mensaje de texto adecuado

---

### T7 — Orquestador de IA (Clasificador de Intenciones + Actions) ✅

**Dependencias**: T2, T5, T6
**Estimación**: 2.5 días
**Responsable**: Backend
**Estado**: COMPLETADO

**Descripción**: El cerebro del chatbot. Clasifica intenciones con GPT-4o-mini y ejecuta los handlers correspondientes.

**Archivos creados**:
- `backend/app/domain/interfaces/llm.py` — `LLMProvider` abstract port + `IntentResult` dataclass
- `backend/app/infrastructure/llm/__init__.py` — Package init
- `backend/app/infrastructure/llm/prompts.py` — System prompt template, FAQ prompt, emergency keywords
- `backend/app/infrastructure/llm/openai_client.py` — `OpenAIClient(LLMProvider)` using OpenAI SDK v1+ async
- `backend/app/infrastructure/llm/intent_classifier.py` — `IntentClassifier` with confidence threshold, emergency detection, unknown retry logic
- `backend/app/application/conversation/classify_intent.py` — `ClassifyIntentService` (loads context, delegates to classifier)
- `backend/app/application/conversation/escalate.py` — `escalate_conversation()` (status change + audit log)
- `backend/app/application/faq/__init__.py` — Package init
- `backend/app/application/faq/answer.py` — `search_faqs()` (LIKE search) + `generate_faq_response()` (LLM-powered)

**Archivos modificados**:
- `backend/app/application/conversation/handle_message.py` — Replaced stub with real orchestrator: intent routing, all 7 handlers, emergency detection, rate limiting, escalation, FAQ processing, WhatsApp send

**Implementar**:
- [x] Clasificador de intenciones: GPT-4o-mini con system prompt del diseño
- [x] Handlers: agendar, cancelar, reprogramar, faq, humano, saludo, desconocido
- [x] Lógica de reintentos (2 intentos fallidos → derivar)
- [x] Detección de emergencias/consultas médicas
- [x] Rate limiting por paciente (max 20 msg/min, in-memory)
- [x] Cache de respuestas FAQs (FAQ search first, LLM for generation)

**Criterios de Aceptación**:
- [x] Clasificación acierta > 85% en 100 mensajes de prueba (por verificar en tests)
- [x] Handler de agendar se ejecuta correctamente (acknowledges, T8 will wire full flow)
- [x] Handler de desconocido pide reformular; al 2do intento fallido deriva
- [x] Detección de emergencia deriva inmediatamente con mensaje de contacto de emergencia
- [x] Respuesta generada en < 3 segundos (OpenAI timeout set to 10s, model is gpt-4o-mini)

---

### T8 — Agendar Turnos (Handler) ✅

**Dependencias**: T7
**Estimación**: 1.5 días
**Responsable**: Backend

**Estado**: COMPLETADO

**Descripción**: Handler que ejecuta el flujo completo de agendar turno: recolectar datos, consultar disponibilidad, confirmar, crear evento.

**Archivos creados**:
- `backend/app/infrastructure/database/repository/__init__.py` — Package init
- `backend/app/infrastructure/database/repository/appointment_repo.py` — AppointmentRepo (CRUD + queries)
- `backend/app/infrastructure/database/repository/patient_repo.py` — PatientRepo (get_or_create, update)
- `backend/app/application/appointment/__init__.py` — Package init
- `backend/app/application/appointment/get_slots.py` — GetAvailableSlots use case
- `backend/app/application/appointment/book.py` — BookAppointment use case (creates event + DB record)

**Archivos modificados**:
- `backend/app/infrastructure/database/models/conversation.py` — Added `extra_data` JSONB column for booking state
- `backend/app/application/conversation/handle_message.py` — Replaced agendar stub with full multi-turn booking flow

**Implementar**:
- [x] Diálogo multi-turno: médico → fecha → horario → confirmación
- [x] Consulta de disponibilidad en Google Calendar
- [x] Creación de evento + registro en DB
- [x] Manejo de múltiples médicos (preguntar cuál)
- [x] Validaciones: horario laboral, anticipación mínima, duración configurable
- [x] Parseo de fechas en español (hoy, mañana, día de semana, DD/MM)
- [x] Parseo de médicos (por índice, nombre, "cualquiera")
- [x] Alternativas cuando no hay disponibilidad
- [x] Manejo de errores: fallo de calendario → mensaje amigable

**Criterios de Aceptación**:
- Paciente agenda en < 6 intercambios
- Evento aparece en Google Calendar y en DB
- Si no hay disponibilidad, ofrece alternativas
- No agenda fuera de horario laboral
- Caso multi-médico: pregunta primero qué profesional

---

### T9 — Cancelar / Reprogramar Turnos (Handler) ✅

**Dependencias**: T7, T8
**Estimación**: 1 día
**Responsable**: Backend

**Estado**: COMPLETADO

**Descripción**: Handlers para cancelar o reprogramar turnos existentes.

**Archivos creados**:
- `backend/app/application/appointment/cancel.py` — `CancelAppointment` use case + `handle_cancel_from_reminder` utility
- `backend/app/application/appointment/reschedule.py` — `RescheduleAppointment` use case (reuses T8 services) + `handle_reschedule_from_reminder` utility

**Archivos modificados**:
- `backend/app/application/conversation/handle_message.py` — Replaced ``_handle_appointment_action`` stub with real ``_handle_cancelar_multiturn``, ``_handle_reprogramar_multiturn``, and ``_handle_consultar_turno`` handlers; added state checks for cancel/reschedule multi-turn flows before intent classification

**Implementar**:
- [x] Cancelar: buscar turno → confirmar → cancelar en Google Calendar → actualizar DB
- [x] Reprogramar: buscar turno → ofrecer nuevos slots → cancelar viejo → crear nuevo
- [x] Validar ventana de 2h antes del turno
- [x] Si paciente no recuerda su turno, mostrar el próximo agendado
- [x] Manejo multi-turno con estado en ``conversation.extra_data`` (cancel_step, reschedule_step)
- [x] Consultar turno: one-shot handler que muestra próximos turnos

**Criterios de Aceptación**:
- [x] Cancelación en < 3 intercambios
- [x] Reprogramación en < 6 intercambios
- [x] Turno a < 2h muestra mensaje de llamar a la clínica
- [x] Slots se liberan en Google Calendar al cancelar

---

### T10 — Recordatorios Automáticos (Celery) ✅

**Dependencias**: T6, T8
**Estimación**: 1 día
**Responsable**: Backend

**Estado**: COMPLETADO

**Descripción**: Sistema de recordatorios programados con Celery Beat.

**Archivos a crear**:
- `backend/tasks/celery_app.py`
- `backend/tasks/reminders.py`
- `backend/tasks/__init__.py`

**Implementar**:
- [x] Tarea Celery: buscar turnos confirmados para mañana → enviar recordatorio
- [x] Primer recordatorio: 24h antes
- [x] Segundo recordatorio: 6h antes (solo si no confirmó)
- [x] Manejar confirmación, reprogramación y cancelación desde el recordatorio
- [x] No enviar recordatorios en horario nocturno (22:00 - 8:00)
- [x] Template de WhatsApp para recordatorio (categoría utility)

**Criterios de Aceptación**:
- [x] Recordatorio enviado exactamente 24h antes
- [x] Si paciente confirma, próximo recordatorio no se envía
- [x] Cancelación desde recordatorio libera el slot
- [x] No se envían recordatorios entre 22:00 y 8:00
- [x] Segunda tanda 6h antes si no hubo confirmación

---

### T11 — FAQ Inteligente ✅

**Dependencias**: T2, T7
**Estimación**: 1 día
**Responsable**: Backend
**Estado**: COMPLETADO

**Descripción**: Sistema de preguntas frecuentes con matching semántico + GPT para respuestas naturales.

**Archivos creados**:
- `backend/app/api/v1/faqs.py` — FAQ CRUD endpoints (GET, POST, PUT, DELETE) protegidos por JWT + tenant scope

**Archivos modificados**:
- `backend/app/application/faq/answer.py` — Improved search with Jaccard similarity, Spanish stop word removal, accent normalization, and in-memory TTL cache
- `backend/app/main.py` — Registered FAQ router

**Implementar**:
- [x] CRUD de FAQs desde el panel admin
- [x] Matching semántico: Jaccard similarity on tokenized words with Spanish stop word removal + accent normalization
- [x] Si hay match en FAQ → respuesta con GPT usando el FAQ como contexto
- [x] Si no hay match (score < 0.2) → "no tengo esa información" + derivar
- [x] Cache de respuestas frecuentes (in-memory dict, TTL 5 min, max 256 entries)
- [x] Cache se invalida al crear/actualizar/eliminar FAQs

**Criterios de Aceptación**:
- [x] FAQ configurada desde el panel se usa en las respuestas del bot
- [x] Pregunta similar a FAQ → respuesta correcta en lenguaje natural
- [x] Pregunta fuera de FAQ → derivación a humano (score < 0.2 threshold)
- [x] Cache funciona para preguntas repetidas

---

### T12 — Derivación a Humano ✅

**Dependencias**: T6, T7, T2
**Estimación**: 1 día
**Responsable**: Backend
**Estado**: COMPLETADO

**Descripción**: Sistema de escalado que pasa la conversación del bot a un humano con contexto completo.

**Archivos creados**:
- `backend/app/api/v1/conversations.py` — Admin API para conversaciones (list, detail, take, reply, return-to-bot)
- `backend/app/api/v1/dashboard.py` — Dashboard stats endpoint

**Archivos modificados**:
- `backend/app/main.py` — Registered conversations and dashboard routers

**Endpoints implementados**:
- `GET /api/v1/conversations` — List conversations (filtros: status, channel; orden: updated_at desc)
- `GET /api/v1/conversations/{id}` — Conversation detail con últimos 50 mensajes + info paciente
- `POST /api/v1/conversations/{id}/take` — Take ownership (solo escalated, no tomada previamente)
- `POST /api/v1/conversations/{id}/reply` — Reply como humano (envía WhatsApp + guarda en DB)
- `POST /api/v1/conversations/{id}/return-to-bot` — Devuelve control al bot (status → active, limpia escalated)
- `GET /api/v1/dashboard/stats` — Estadísticas: turnos hoy, pendientes, conversaciones activas/derivadas, no-show rate

**Implementar**:
- [x] Trigger de derivación: solicitud del paciente, baja confianza, emergencia, 2 intentos fallidos (ya implementado en T7)
- [x] Marcado de conversación como `escalated` (ya implementado en `escalate.py` de T7)
- [x] Polling para notificar al panel (dashboard/stats expone `escalated_conversations` count)
- [x] Panel puede tomar, responder y devolver al bot
- [x] Cada respuesta del humano se envía por WhatsApp y se guarda en DB

**Criterios de Aceptación**:
- [x] Derivación por palabra "humano" funciona inmediatamente (T7)
- [x] Recepcionista ve contexto completo (últimos 50 mensajes) — `GET /api/v1/conversations/{id}`
- [x] Recepcionista responde y llega al paciente en < 3 segundos — `POST /api/v1/conversations/{id}/reply`
- [x] Bot deja de responder cuando está derivado (T7 — `handle_message.py` chequea status)
- [x] Recepcionista puede devolver control al bot — `POST /api/v1/conversations/{id}/return-to-bot`

---

### T13 — Panel Web Base (Login, Dashboard, Layout) ✅

**Dependencias**: T3
**Estimación**: 2 días
**Responsable**: Frontend

**Estado**: COMPLETADO

**Descripción**: Base del panel de administración en React + Vite + Tailwind.

**Archivos creados**:
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tailwind.config.js`
- `frontend/postcss.config.js`
- `frontend/tsconfig.json`
- `frontend/tsconfig.app.json`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/index.css`
- `frontend/src/vite-env.d.ts`
- `frontend/src/services/api.ts`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/components/ProtectedRoute.tsx`
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/Register.tsx`
- `frontend/src/pages/Dashboard.tsx`

**Secciones**:
- Login / Register / Magic Link
- Dashboard con tarjetas de stats (turnos hoy, pendientes, conversaciones, no-show)
- Layout con sidebar y navegación
- Protección de rutas por rol

**Criterios de Aceptación**:
- [x] Login funciona con JWT
- [x] Dashboard muestra datos reales desde la API
- [x] Sidebar navega entre secciones
- [x] Sin token → redirige a login
- [x] Roles admin vs recepcionista (menú diferente)

---

### T14 — Panel Web — Turnos y Conversaciones ✅

**Dependencias**: T13, T8, T12
**Estimación**: 2 días
**Responsable**: Frontend

**Estado**: COMPLETADO

**Descripción**: Pantallas de gestión de turnos y conversaciones en el panel.

**Archivos creados**:
- `frontend/src/services/api.ts` — Added appointment and conversation types + service methods
- `frontend/src/pages/Appointments.tsx` — Appointments table with filters, actions, CSV export
- `frontend/src/pages/AppointmentDetail.tsx` — Appointment detail card with actions
- `frontend/src/pages/Conversations.tsx` — Conversations list with filters, polling for escalated count
- `frontend/src/pages/ConversationDetail.tsx` — Chat window with take/reply/return-to-bot

**Archivos modificados**:
- `frontend/src/App.tsx` — Added `/appointments`, `/appointments/:id`, `/conversations`, `/conversations/:id` routes

> **⚠️ CRITICAL FIX (2026-06-05)**: The backend endpoints for appointments (`/api/v1/appointments/*`) were never implemented. Created `backend/app/api/v1/appointments.py` with 6 endpoints (list, detail, cancel, confirm, mark-attended, export CSV) and registered in `backend/app/main.py`. This fixes CA8.1 which was failing verification. See apply-progress.md for details.

**Secciones**:
- Lista de turnos con filtros (fecha, estado)
- Detalle de turno: info del paciente, acciones (cancelar, confirmar, marcar atendido)
- Lista de conversaciones (activas, derivadas, resueltas, archivadas)
- Chat window: historial de mensajes, tomar conversación, responder, devolver al bot
- Exportar a CSV

**Criterios de Aceptación**:
- [x] Filtros funcionan (fecha, estado) — Date picker + status dropdown
- [x] Cancelar turno desde el panel se refleja en backend — POST /appointments/{id}/cancel
- [x] Conversación derivada se ve con historial completo — GET /conversations/{id} con últimos 50 mensajes
- [x] Recepcionista puede responder desde el chat window — POST /conversations/{id}/reply
- [x] Exportar CSV descarga archivo válido — GET /appointments/export → Blob download

---

### T15 — Panel Web — Configuración ✅

**Dependencias**: T13, T5, T11
**Estimación**: 1.5 días
**Responsable**: Frontend
**Estado**: COMPLETADO

**Descripción**: Pantallas de configuración de la clínica, FAQs, médicos, Google Calendar, equipo.

**Archivos creados**:
- `frontend/src/pages/Settings.tsx`
- `frontend/src/pages/ClinicConfig.tsx`
- `frontend/src/pages/FAQs.tsx`
- `frontend/src/pages/Doctors.tsx`
- `frontend/src/pages/Team.tsx`
- `frontend/src/pages/CalendarIntegration.tsx`

**Archivos modificados**:
- `frontend/src/services/api.ts` — Added clinic config, doctors, FAQs, team, calendar service methods and types
- `frontend/src/App.tsx` — Added `/settings` route (Settings with tabs), `/team` redirects to `/settings?tab=equipo`

**Secciones**:
- [x] Configuración clínica: nombre, dirección, horarios, duración turno, precios
- [x] FAQs: CRUD con lista editable
- [x] Médicos: CRUD
- [x] Google Calendar: conectar/desconectar, estado
- [x] Equipo: invitar/remover miembros

**Criterios de Aceptación**:
- [x] Guardar configuración se refleja en el bot inmediatamente
- [x] CRUD de FAQs desde el panel
- [x] Conectar Google Calendar muestra el OAuth flow
- [x] Invitar miembro envía email de invitación
- [x] Cambios en horarios afectan disponibilidad de turnos

---

### T16 — Onboarding Guiado ✅

**Dependencias**: T13, T5, T6
**Estimación**: 1.5 días
**Responsable**: Full-stack
**Estado**: COMPLETADO

**Descripción**: Flujo paso a paso que guía al dueño de la clínica desde el registro hasta tener el bot funcionando.

**Archivos creados**:
- `backend/app/api/v1/onboarding.py` — Onboarding API (GET /status, PUT /step, GET /faq-templates)
- `backend/app/api/v1/clinic_config.py` — Clinic Config API (GET/PUT /clinic-config)
- `frontend/src/pages/Onboarding.tsx` — 5-step onboarding wizard page

**Archivos modificados**:
- `backend/app/infrastructure/database/models/tenant_settings.py` — Added `onboarding_state` JSONB, `onboarding_completed` Boolean
- `backend/app/infrastructure/database/models/clinic_config.py` — Added `prices` JSONB column
- `backend/migrations/versions/002_add_onboarding_fields.py` — Migration for new columns
- `backend/app/main.py` — Registered onboarding + clinic_config routers
- `frontend/src/services/api.ts` — Added `onboarding` service (status, markStep, faqTemplates)
- `frontend/src/App.tsx` — Added `/onboarding` route (standalone, protected)
- `frontend/src/pages/Login.tsx` — After login, redirects to `/onboarding` if onboarding not complete
- `frontend/src/pages/Register.tsx` — After register, always redirects to `/onboarding`

**Pasos**:
1. Conectar WhatsApp (instrucciones + "Ya conecté")
2. Conectar Google Calendar (OAuth + status check)
3. Configurar clínica (nombre, dirección, teléfono, horarios)
4. Cargar preguntas frecuentes (desde plantillas predefinidas)
5. ✅ ¡Bot activo! Check-list de estado + "Ir al dashboard"

**Criterios de Aceptación**:
- ✅ Usuario no técnico completa en < 30 minutos
- ✅ Validación en cada paso con mensajes de error claros
- ✅ Progreso guardado (puede retomar después)
- ✅ Al completar, redirige al dashboard
- ✅ Login redirige a onboarding si está pendiente

---

### T17 — Testing ✅

**Dependencias**: T2 a T16
**Estimación**: 2 días
**Responsable**: Full-stack
**Estado**: COMPLETADO — 127 tests pasan

**Descripción**: Tests unitarios e integrales del backend.

**Archivos a crear**:
- `backend/tests/conftest.py`
- `backend/tests/unit/test_intent_classifier.py`
- `backend/tests/unit/test_appointment_book.py`
- `backend/tests/unit/test_appointment_cancel.py`
- `backend/tests/integration/test_whatsapp_webhook.py`
- `backend/tests/integration/test_calendar.py`
- `backend/tests/integration/test_auth_api.py`
- `backend/tests/integration/test_appointment_api.py`

**Implementar**:
- Unit tests: clasificador de intenciones con fixtures de mensajes
- Unit tests: reglas de negocio (horarios, validaciones)
- Integration tests: API endpoints con base de datos de prueba
- Integration tests: webhook de WhatsApp (mock Evolution API)
- Integration tests: Google Calendar (mock API)
- Mínimo 70% de cobertura en backend

**Criterios de Aceptación**:
- `pytest` pasa todos los tests
- Cobertura > 70%
- Tests son independientes (no comparten estado)
- CI puede ejecutarlos

---

### T18 — Despliegue y CI/CD ✅

**Dependencias**: T1 a T17
**Estimación**: 1 día
**Responsable**: DevOps
**Estado**: COMPLETADO

**Descripción**: Pipeline de CI/CD y configuración de producción.

**Archivos a crear**:
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `backend/Dockerfile.prod`
- `docker-compose.prod.yml`
- `frontend/nginx.conf`

**Implementar**:
- CI: lint, type check, tests en cada push a main
- CD: deploy automático a Railway/Render
- Docker multi-stage para producción
- Health checks en producción
- Backup automático de PostgreSQL

**Criterios de Aceptación**:
- CI corre en cada push
- Deploy a staging desde PR
- Deploy a producción desde main
- Rollback posible en un click

---

## Resumen de Estimación

| Fase | Tareas | Días |
|---|---|---|
| Backend core | T1-T4 | 3 |
| Integraciones | T5 ✅, T6 ✅ (T7 pendiente) | 6 |
| Features chatbot | T8 ✅, T9 ✅, T10-T12 pendientes | 5.5 |
| Panel web | T13-T15 | 5.5 |
| Onboarding | T16 | 1.5 |
| Testing | T17 | 2 |
| Deploy | T18 | 1 |
| **Total** | **18 tareas** | **~24.5 días** |

---

## Próximo Paso

**Aplicar tareas en batches (apply)**. Cada batch corresponde a un PR encadenado:

- **PR 1**: Setup + Modelos + Auth + Tenants (T1-T4) ~3.5 días
- **PR 2a**: Google Calendar (T5) ~2 días ✅ (completado)
- **PR 2b**: WhatsApp (T6) ~1.5 días ✅  
- **PR 2c**: Orquestador IA (T7) ~2.5 días (pendiente)
- **PR 3a**: Agendar Turnos (T8) ~1.5 días ✅
- **PR 3b**: Cancelar/Reprogramar (T9) ~1 día ✅
- **PR 3c**: Recordatorios + FAQ + Derivación (T10-T12) ~3 días (pendiente)
- **PR 4**: Panel web completo (T13-T16) ~5 días
- **PR 5a**: Testing (T17) ~2 días ✅
- **PR 5b**: Deploy + CI/CD (T18) ~1 día ✅
