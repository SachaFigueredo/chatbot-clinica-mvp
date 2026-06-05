# Especificaciones — Chatbot SaaS para Clínicas de Medicina General

**Cambio**: chatbot-clinica-mvp
**Fase**: Spec
**Depende de**: proposal.md
**Fecha**: 2026-06-04

---

## Resumen de Features (MVP)

| # | Feature | Prioridad | Dependencias |
|---|---|---|---|
| F1 | Chat IA por WhatsApp | P0 | Ninguna |
| F2 | Agendar turnos | P0 | F1, F7 (Google Calendar) |
| F3 | Reprogramar / Cancelar turnos | P0 | F2 |
| F4 | Recordatorios automáticos | P0 | F2, F7 |
| F5 | FAQ inteligente | P0 | F1 |
| F6 | Derivación a humano | P0 | F1 |
| F7 | Google Calendar sincronizado | P0 | Ninguna |
| F8 | Panel web de administración | P0 | F2, F6 |
| F9 | Multi-tenencia | P0 | Ninguna |
| F10 | Onboarding guiado | P1 | F8 |

---

## F1 — Chat IA por WhatsApp

### Propósito
El paciente puede conversar con la clínica por WhatsApp usando lenguaje natural, y el bot entiende la intención para ejecutar acciones.

### Actores
- **Paciente**: persona que escribe al WhatsApp de la clínica
- **Bot**: sistema que procesa y responde mensajes

### Flujo Principal
1. Paciente envía mensaje de texto al número WhatsApp de la clínica
2. Evolution API recibe el mensaje y lo envía como webhook POST a FastAPI
3. FastAPI identifica el tenant por el número destino
4. El orquestador de IA clasifica la intención del mensaje:
   - `agendar` — quiere sacar turno
   - `consultar_turno` — quiere ver sus turnos
   - `reprogramar` — quiere cambiar un turno
   - `cancelar` — quiere cancelar un turno
   - `faq` — pregunta información de la clínica
   - `humano` — quiere hablar con una persona
   - `saludo` — saludo genérico
   - `desconocido` — intención no reconocida
5. Según la intención, el orquestador delega al handler correspondiente
6. El handler ejecuta la acción (consulta agenda, busca FAQ, etc.)
7. Se genera respuesta con GPT-4o-mini usando el contexto recuperado
8. Se envía la respuesta vía Evolution API al paciente

### Reglas de Negocio
- RN1.1: El bot debe responder en < 3 segundos para mantener la conversación fluida
- RN1.2: El historial de conversación se mantiene por sesión (24h desde el último mensaje del paciente)
- RN1.3: Si el paciente envía múltiples intenciones en un mensaje, se prioriza la primera detectable
- RN1.4: El bot nunca da consejo médico. Si detecta una consulta clínica, deriva a humano con el mensaje textual
- RN1.5: El bot se presenta siempre con el nombre de la clínica, no con un nombre genérico
- RN1.6: Toda conversación se almacena en DB para trazabilidad

### Escenarios

**Happy path**: Paciente: "Hola, quiero sacar un turno" → Bot clasifica `agendar` → pasa a F2

**Edge cases**:
- Mensaje solo con emojis → clasificar como `desconocido`, responder amablemente pidiendo más contexto
- Mensaje en mayúsculas sostenidas → procesar normalmente
- Audio o imagen → responder que solo puede procesar texto, derivar a humano si es urgente
- Paciente escribe a las 3 AM → el bot responde igual, pero agenda solo en horarios configurados

### Criterios de Aceptación
- CA1.1: El bot responde cualquier mensaje de texto en < 3 segundos
- CA1.2: La clasificación de intención acierta > 85% en pruebas con 100 mensajes variados
- CA1.3: El historial de la conversación es recuperable desde el panel web
- CA1.4: El bot rechaza dar consejo médico y deriva a humano

---

## F2 — Agendar Turnos

### Propósito
El paciente agenda un turno conversando con el bot, sin intervención humana. El turno se refleja en Google Calendar del médico y en la base de datos local.

### Actores
- **Paciente**
- **Bot**
- **Google Calendar**

### Flujo Principal
1. Bot clasifica intención `agendar` (desde F1)
2. Bot solicita al paciente: especialidad/médico (si hay varios), fecha preferida, y motivo de consulta (opcional)
3. Bot consulta Google Calendar del médico correspondiente para horarios disponibles
4. Bot presenta opciones al paciente: "Tenés disponibles: martes 10:00, 11:00, 11:30. ¿Cuál te queda mejor?"
5. Paciente selecciona horario
6. Bot confirma: "Perfecto, te agendé para el martes 10:00 con el Dr. García. Te enviamos un recordatorio 24h antes."
7. Bot crea el evento en Google Calendar con datos del paciente (nombre, teléfono, motivo)
8. Bot guarda el turno en la base de datos local con estado `confirmado` y el `google_event_id`

### Reglas de Negocio
- RN2.1: La duración del turno la define cada clínica en su configuración (default: 20 min)
- RN2.2: El bot agenda solo dentro del horario de atención configurado (ej: lunes a viernes 8-17, sábados 8-12)
- RN2.3: No se pueden agendar turnos con menos de 1 hora de anticipación
- RN2.4: No se pueden agendar turnos para más de 60 días en el futuro
- RN2.5: Google Calendar es la fuente de verdad de disponibilidad. La DB local es un cache de tracking
- RN2.6: Si Google Calendar no está disponible, el bot informa "sistema temporalmente fuera de servicio" y deriva a humano
- RN2.7: Antes de confirmar, el bot debe repetir la información y pedir confirmación al paciente

### Escenarios

**Happy path**: Paciente agenda en 3 intercambios (saludo → elige horario → confirma)

**Alternativo A — Múltiples médicos**:
1. Bot: "¿Con qué profesional querés turno?"
2. Paciente: "Con la Dra. Pérez"
3. Bot busca slots de la Dra. Pérez específicamente

**Alternativo B — Sin disponibilidad**:
1. Bot busca y no encuentra slots en los próximos 7 días
2. Bot: "No tengo turnos disponibles para esta semana. La próxima semana tengo disponible el lunes 15 a las 9:00, 10:00..."
3. Si no hay nada en 30 días: "No hay turnos disponibles en las próximas semanas. ¿Querés que te avisemos si se libera alguno?" (lista de espera — para V2, por ahora deriva a humano)

**Edge cases**:
- Paciente pide un horario que no existe (ej: "domingo a las 3 AM") → Bot responde con horarios válidos
- Paciente cancela a medio flujo → La sesión expira a los 5 min sin respuesta
- Google Calendar devuelve error → Reintentar 1 vez, si falla derivar a humano

### Criterios de Aceptación
- CA2.1: Paciente agenda un turno en menos de 6 intercambios con el bot
- CA2.2: El evento creado en Google Calendar tiene nombre, teléfono y motivo del paciente
- CA2.3: El turno aparece en el panel web inmediatamente
- CA2.4: Si no hay disponibilidad, el bot lo comunica claramente y ofrece alternativas

---

## F3 — Reprogramar / Cancelar Turnos

### Propósito
El paciente puede modificar o cancelar su turno por WhatsApp.

### Actores
- **Paciente**
- **Bot**
- **Google Calendar**

### Flujo — Cancelar
1. Bot clasifica intención `cancelar`
2. Bot: "Veo que tenés un turno agendado para el martes 10:00 con el Dr. García. ¿Confirmás que querés cancelarlo?"
3. Paciente confirma
4. Bot cancela el evento en Google Calendar
5. Bot actualiza estado en DB local a `cancelado_por_paciente`
6. Bot: "Listo, tu turno del martes 10:00 fue cancelado. Si querés agendar uno nuevo, decime."

### Flujo — Reprogramar
1. Bot clasifica intención `reprogramar`
2. Bot muestra turno actual y pregunta nueva fecha
3. Sigue flujo de F2 (agendar) para el nuevo slot
4. Una vez confirmado el nuevo turno, cancela el anterior en Google Calendar
5. Bot actualiza registros: viejo → `reprogramado`, nuevo → `confirmado`

### Reglas de Negocio
- RN3.1: Solo se pueden cancelar/reprogramar turnos con más de 2 horas de anticipación
- RN3.2: Si el turno es en menos de 2 horas, bot informa que debe llamar a la clínica
- RN3.3: Se requiere confirmación explícita del paciente antes de cualquier modificación
- RN3.4: Un turno `cancelado` o `reprogramado` libera el slot en Google Calendar

### Escenarios

**Happy path cancelar**: 2 intercambios (solicitud → confirmación → confirmado)
**Happy path reprogramar**: 4-5 intercambios (solicitud → nuevo horario → confirmación)

**Edge case — Paciente no recuerda el turno**: Bot busca por número de teléfono y muestra el próximo turno agendado

### Criterios de Aceptación
- CA3.1: Cancelación toma < 3 intercambios
- CA3.2: Reprogramación toma < 6 intercambios
- CA3.3: Google Calendar se actualiza en < 10 segundos tras la confirmación
- CA3.4: Turnos a < 2h no se pueden modificar por WhatsApp

---

## F4 — Recordatorios Automáticos

### Propósito
Reducir ausentismo enviando recordatorios por WhatsApp con confirmación.

### Actores
- **Bot**
- **Paciente**
- **Cron scheduler**

### Flujo Principal
1. Un cron job se ejecuta cada hora
2. Busca turnos con estado `confirmado` para el día siguiente (24h antes del turno)
3. Para cada turno, envía un mensaje por WhatsApp:
   "📅 *Recordatorio de turno*
   Hola [nombre], te recordamos que tenés turno mañana [fecha] a las [hora] con [médico] en [dirección].
   Respondé:
   ✅ *Confirmar* — voy a asistir
   🔄 *Reprogramar* — quiero cambiar la fecha
   ❌ *Cancelar* — no voy a poder ir"
4. Si el paciente responde ✅ → DB: `confirmado`, no se hace nada más
5. Si responde 🔄 → inicia flujo de F3 (reprogramar)
6. Si responde ❌ → inicia flujo de F3 (cancelar)
7. Si NO responde → 6h antes del turno, enviar segundo recordatorio
8. Si tampoco responde al segundo → DB: `sin_confirmar`, el médico ve en el panel que no confirmó

### Reglas de Negocio
- RN4.1: Primer recordatorio: 24h antes del turno
- RN4.2: Segundo recordatorio: 6h antes del turno (solo si no confirmó el primero)
- RN4.3: No enviar recordatorios entre 22:00 y 8:00 (respetar silencio nocturno)
- RN4.4: Si el turno es antes de las 10:00, el primer recordatorio se envía el día anterior a las 9:00 como mínimo
- RN4.5: Los mensajes de recordatorio usan template de WhatsApp categoría `utility` (gratis si el paciente inició conversación antes)
- RN4.6: El paciente puede optar por no recibir recordatorios (debe configurarse en el panel)

### Escenarios

**Happy path**: Paciente recibe recordatorio 24h antes, confirma ✅, no se envía segundo

**Alternativo — Sin confirmación**: No responde → segundo recordatorio 6h antes → tampoco responde → DB `sin_confirmar`

**Alternativo — Paciente cancela por recordatorio**: Recibe recordatorio, responde ❌, turno cancelado, se libera slot

### Criterios de Aceptación
- CA4.1: Recordatorio se envía exactamente 24h antes del turno
- CA4.2: Si paciente confirma, no se envía segundo recordatorio
- CA4.3: Si paciente cancela desde el recordatorio, el slot se libera en < 10 segundos
- CA4.4: No se envían recordatorios en horario nocturno

---

## F5 — FAQ Inteligente

### Propósito
El paciente puede preguntar información de la clínica y el bot responde con los datos configurados.

### Actores
- **Paciente**
- **Bot**

### Flujo Principal
1. Bot clasifica intención `faq`
2. Bot busca en la base de conocimiento de la clínica (FAQ, horarios, precios, etc.)
3. GPT-4o-mini genera respuesta basada en el contexto recuperado
4. Bot envía respuesta

### Contenido Configurable por Clínica
- Horarios de atención
- Dirección y sucursales
- Precios de consulta (particular, obras sociales / prepagas)
- Preparación para estudios (ej: "¿Hay que ir en ayunas?")
- Documentación necesaria (DNI, orden médica, etc.)
- Formas de pago aceptadas
- Tiempo estimado de atención
- Política de cancelación

### Reglas de Negocio
- RN5.1: El FAQ se configura desde el panel web por cada clínica
- RN5.2: El bot NUNCA inventa información que no esté en la base de conocimiento de la clínica
- RN5.3: Si la pregunta está fuera de la base de conocimiento, el bot dice "No tengo esa información, consultá con recepción" y deriva a humano
- RN5.4: Las respuestas pueden ser texto plano, listas, o enlaces
- RN5.5: El bot usa la información configurada + contexto de GPT para responder, no respuestas fijas

### Criterios de Aceptación
- CA5.1: El bot responde correctamente preguntas sobre horarios, dirección y precios
- CA5.2: El bot NO responde preguntas fuera de su base de conocimiento (deriva a humano)
- CA5.3: Cada clínica tiene su propio FAQ independiente
- CA5.4: Las respuestas son en lenguaje natural, no texto robótico

---

## F6 — Derivación a Humano

### Propósito
Cuando el bot no puede resolver o el paciente lo solicita, la conversación pasa al panel de recepción con contexto completo.

### Actores
- **Paciente**
- **Bot**
- **Recepcionista** (humano)

### Flujo Principal
1. Se detecta una condición de derivación:
   - Paciente escribe "hablar con una persona", "humano", "atención", etc.
   - Bot clasifica intención como `desconocido` con baja confianza
   - Bot detecta posible consulta médica (palabras clave: "dolor", "síntoma", "emergencia")
   - Se alcanzó el límite de reintentos del bot (2 intentos fallidos)
2. Bot responde: "Te paso con recepción así te pueden ayudar mejor. Un momento por favor."
3. La conversación se marca como `derivada` en DB
4. Aparece notificación en el panel web de recepción con:
   - Nombre y teléfono del paciente
   - Historial completo de la conversación
   - Intención original detectada
   - Motivo de la derivación
5. Recepcionista abre la conversación y responde desde el panel
6. Las respuestas del recepcionista se envían por WhatsApp usando el mismo número de la clínica

### Reglas de Negocio
- RN6.1: El bot deriva automáticamente si detecta palabras clave de emergencia médica: "emergencia", "urgencia", "dolor fuerte", "accidente", "sangrado"
- RN6.2: En caso de emergencia detectada, el bot indica "Si es una emergencia, llamá al [teléfono de emergencias configurado]" además de derivar
- RN6.3: La derivación incluye siempre los últimos 50 mensajes de la conversación como contexto
- RN6.4: Una vez derivado, el bot deja de responder en esa conversación hasta que el humano devuelva el control
- RN6.5: El recepcionista puede devolver el control al bot cuando la consulta esté resuelta

### Criterios de Aceptación
- CA6.1: Derivación por solicitud del paciente toma < 5 segundos
- CA6.2: El recepcionista ve el historial completo al abrir la conversación
- CA6.3: El recepcionista puede responder desde el panel y el mensaje llega al paciente por WhatsApp
- CA6.4: Emergencias detectadas disparan mensaje de contacto de emergencia

---

## F7 — Google Calendar Sincronizado

### Propósito
Google Calendar es la fuente de verdad para disponibilidad de turnos. Cada médico/clínica tiene su calendario conectado.

### Actores
- **Bot**
- **Google Calendar API**
- **Administrador de clínica**

### Flujo — Conexión Inicial
1. Admin va al panel web → Configuración → Conectar Google Calendar
2. Click en "Conectar con Google"
3. OAuth 2.0 flow: admin autoriza permisos (ver calendarios, crear/editar eventos)
4. Se almacena el refresh token en DB (encriptado) para operaciones automáticas
5. Admin selecciona qué calendario usar de su cuenta de Google
6. Conexión exitosa → el bot ya puede leer y escribir en ese calendario

### Flujo — Lectura de Disponibilidad
1. Bot necesita buscar slots libres
2. Consulta Google Calendar API: eventos en el rango de fechas solicitado
3. Calcula slots libres = bloques de duración_configurada - eventos_ocupados - bloques_fuera_de_horario
4. Devuelve lista de slots disponibles

### Flujo — Creación de Evento
1. Bot confirma turno con paciente
2. Crea evento en Google Calendar con:
   - Título: `[Paciente] Nombre Apellido`
   - Descripción: `Tel: +5491112345678\nMotivo: [motivo]`
   - Duración: configurada por clínica
   - Color/etiqueta: según corresponda
3. Guarda `google_event_id` en DB local
4. Si falla la creación, reintenta 1 vez. Si vuelve a fallar → deriva a humano

### Reglas de Negocio
- RN7.1: Google Calendar es la fuente de verdad. La DB local nunca escribe sin confirmación de Google
- RN7.2: Se usa OAuth 2.0 con refresh tokens. Si el token expira y no se puede refrescar, se notifica al admin
- RN7.3: El bot respeta los bloques de "no disponible" que el médico marque en su calendario
- RN7.4: Eventos creados por el bot se etiquetan con un prefijo `[Bot]` para identificarlos
- RN7.5: Si el calendario tiene un evento recurrente (ej: "Bloque administrativo todos los jueves 14-16"), se respeta

### Escenarios

**Happy path**: Admin conecta Google Calendar en 2 clics, bot lee y escribe sin problemas

**Error — Token expirado**: Bot no puede refrescar → notifica admin: "Tu conexión con Google Calendar expiró. Conectala de nuevo desde el panel."

**Error — Calendario eliminado**: Admin borró el calendario → bot detecta 404 → notifica admin

### Criterios de Aceptación
- CA7.1: Admin conecta Google Calendar desde el panel en < 5 minutos
- CA7.2: Bot consulta disponibilidad correctamente (excluye horarios ocupados)
- CA7.3: Evento creado por bot aparece en Google Calendar en < 5 segundos
- CA7.4: Si el token expira, se notifica al admin por WhatsApp y email
- CA7.5: El bot no agenda en horarios bloqueados

---

## F8 — Panel Web de Administración

### Propósito
El administrador de la clínica gestiona turnos, conversaciones, y configuración desde un panel web.

### Secciones del Panel

#### 8.1 Login / Autenticación
- Login con email + contraseña
- Opción de magic link por email
- Recuperación de contraseña
- Roles: `admin` (dueño, acceso total), `recepcionista` (turnos + conversaciones, no configuración)

#### 8.2 Dashboard (Inicio)
- Tarjetas: turnos hoy, turnos pendientes de confirmar, conversaciones sin leer, % de no-show
- Lista de turnos del día (próximos 10)
- Actividad reciente (últimas 5 conversaciones)

#### 8.3 Turnos
- Tabla con todos los turnos (filtros: fecha, médico, estado)
- Estados: `pendiente`, `confirmado`, `cancelado_por_paciente`, `cancelado_por_clinica`, `reprogramado`, `sin_confirmar`, `atendido`
- Acciones: crear turno manual, cancelar, re-agendar, marcar como atendido
- Exportar a CSV

#### 8.4 Conversaciones
- Lista de conversaciones activas y archivadas
- Filtro: bot / derivadas a humano / todas
- Al abrir: historial completo de mensajes (bot + paciente + recepcionista)
- Tomar conversación: el recepcionista reclama y empieza a responder
- Devolver al bot: cuando la consulta está resuelta

#### 8.5 Configuración de la Clínica
- Nombre, dirección, teléfono, email
- Horarios de atención (por día, editable)
- Duración de turno (default 20 min)
- Médicos/profesionales (nombre, especialidad, calendario asociado)
- Precios (particular, obras sociales)
- FAQ editable (preguntas + respuestas)
- Mensaje de bienvenida personalizable
- Integración: Google Calendar (conectar/desconectar)
- Número WhatsApp conectado

#### 8.6 Miembros del Equipo
- Invitar/remover miembros
- Roles: admin, recepcionista

#### 8.7 Configuración de la Cuenta
- Plan actual, fecha de facturación
- Historial de pagos (para V2)

### Reglas de Negocio
- RN8.1: El panel es responsivo (funciona en mobile)
- RN8.2: Las acciones del panel (cancelar turno, etc.) se reflejan en Google Calendar en tiempo real
- RN8.3: El panel usa los mismos endpoints de API que el bot (no hay lógica duplicada)
- RN8.4: Los cambios en configuración (horarios, FAQ) toman efecto inmediato
- RN8.5: Sesión expira después de 24h de inactividad

### Criterios de Aceptación
- CA8.1: Admin puede ver, crear y cancelar turnos desde el panel
- CA8.2: Recepcionista puede tomar y responder conversaciones derivadas
- CA8.3: Admin puede configurar horarios, médicos, FAQ y precios
- CA8.4: Los cambios en configuración se reflejan en el comportamiento del bot inmediatamente
- CA8.5: El panel funciona en Chrome, Firefox, Safari y Edge (últimas 2 versiones)

---

## F9 — Multi-Tenencia

### Propósito
Cada clínica es un tenant aislado con sus propios datos, configuración, y número de WhatsApp.

### Estrategia
- **Aislamiento por `tenant_id`**: cada tabla tiene una columna `tenant_id`
- Cada tenant tiene:
  - Una o más cuentas de usuario (admin, recepcionista)
  - Un número de WhatsApp conectado
  - Un calendario de Google (o varios, uno por médico)
  - Su propia configuración (horarios, FAQ, precios, médicos)
  - Sus propios pacientes (identificados por número de teléfono)
  - Sus propias conversaciones y turnos

### Identificación de Tenant
- Cuando llega un webhook de WhatsApp, se identifica el tenant por el número destino (el número de WhatsApp de la clínica)
- En el panel web, el admin ya está autenticado y su sesión tiene el `tenant_id`

### Reglas de Negocio
- RN9.1: Un paciente registrado en un tenant NO existe para otros tenants
- RN9.2: Las cuentas de admin/recepcionista pertenecen a un solo tenant
- RN9.3: No existe "super-admin" para ver todos los tenants en MVP (para V2)
- RN9.4: Los datos de un tenant deben ser física o lógicamente separables para facilitar exportación/eliminación

### Criterios de Aceptación
- CA9.1: Dos clínicas pueden operar simultáneamente sin interferencia de datos
- CA9.2: Admin de clínica A no puede ver datos de clínica B
- CA9.3: Al eliminar un tenant, todos sus datos se eliminan (soft delete)

---

## F10 — Onboarding Guiado (P1)

### Propósito
El dueño de la clínica puede configurar su cuenta y empezar a operar en < 30 minutos sin asistencia.

### Flujo
1. Admin se registra (email, contraseña, nombre de clínica)
2. Paso 1: Conectar WhatsApp (escanea QR, conecta número existente o solicita uno nuevo)
3. Paso 2: Conectar Google Calendar (OAuth, seleccionar calendario)
4. Paso 3: Configurar clínica (horarios, dirección, médicos)
5. Paso 4: Configurar preguntas frecuentes (o cargar desde plantilla)
6. Paso 5: ¡Listo! El bot ya está activo
7. Check-list visual de lo que falta configurar

### Criterios de Aceptación
- CA10.1: Un usuario no técnico completa el onboarding en < 30 minutos
- CA10.2: Cada paso tiene validación y mensajes de error claros
- CA10.3: Se puede salvar el progreso y continuar después

---

## Reglas de Negocio Transversales

### Privacidad y Datos
- RT1: Los números de teléfono de pacientes se almacenan con hash (solo el último dígito en claro para identificación)
- RT2: Las conversaciones se almacenan por 90 días, luego se anonimizan
- RT3: El consentimiento del paciente se registra en la primera interacción

### Operación
- RT4: El bot no opera fuera del horario de atención para acciones que requieren confirmación humana (cancelaciones exprés sí, pero reprogramaciones complejas pueden necesitar revisión)
- RT5: Todas las acciones del bot son auditables (quién, qué, cuándo)
- RT6: Los template messages de WhatsApp deben ser aprobados por Meta antes de usarse

---

*Próximo paso: Diseño técnico (arquitectura, base de datos, API)*
