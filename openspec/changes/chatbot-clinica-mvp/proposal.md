# Propuesta: Chatbot SaaS para Clínicas de Medicina General

**Cambio**: chatbot-clinica-mvp
**Estado**: Propuesta
**Fecha**: 2026-06-04

---

## 1. Intención

**Problema**: Las clínicas de medicina general pequeñas y medianas pierden pacientes porque no pueden contestar el WhatsApp 24/7, gestionar turnos eficientemente, ni reducir el ausentismo (20-30% de no-shows). Las soluciones existentes son caras ($200-500/mes) o demasiado técnicas.

**Solución**: Un SaaS multi-tenencia que le da a cada clínica un asistente IA en WhatsApp que:
- Atiende pacientes 24/7 con lenguaje natural
- Agenda, reprograma y cancela turnos
- Envía recordatorios automáticos
- Responde preguntas frecuentes
- Deriva a humano cuando es necesario

**Para quién**: Clínicas de medicina general en LATAM con 1-10 médicos, que atienden 100-500 turnos/mes. Dueños o administradores con poco conocimiento técnico.

**Modelo de negocio**: SaaS por suscripción mensual, tres planes escalando por cantidad de médicos.

---

## 2. Alcance

### Incluido en MVP

| Feature | Prioridad | Descripción |
|---|---|---|
| Chat IA por WhatsApp | P0 | Conversación natural con GPT-4o-mini. Paciente escribe y el bot entiende intención |
| Agendar turnos | P0 | El bot busca disponibilidad en Google Calendar y agenda automáticamente |
| Reprogramar / Cancelar | P0 | El paciente puede cambiar o cancelar su turno por chat |
| Recordatorios automáticos | P0 | WhatsApp 24h antes + confirmación. Si no confirma, re-intenta |
| FAQ automático | P0 | Responde horarios, dirección, precios, preparación para consultas |
| Derivación a humano | P0 | Si el bot no puede o el paciente pide, pasa a la recepción con contexto |
| Panel web de administración | P0 | Ver turnos, conversaciones, configurar clínica (horarios, precios, FAQ) |
| Google Calendar sincronizado | P0 | Bidireccional: lo que agenda el bot aparece en el calendario del médico |
| Multi-tenencia | P0 | Cada clínica es un tenant con sus propios datos y configuración |
| Onboarding guiado | P1 | El dueño configura la clínica en < 30 min: nombre, horarios, precios, FAQ |

### Excluido de MVP

| Feature | Para después | Razón |
|---|---|---|
| Pagos desde WhatsApp | V2 | Stripe/MercadoPago. Complejidad regulatoria |
| Agente de voz | V2 | ElevenLabs. Canal adicional, no crítico |
| Integración con sistemas de historia clínica (HIS) | V2 | Requiere integración con cada sistema |
| App mobile nativa | V2 | El panel web + WhatsApp cubre el 90% |
| Lista de espera automática | V2 | Útil pero no indispensable para validar |
| Encuestas post-consulta | V2 | Diferenciador, no esencial |
| Multi-idioma | V2 | Español primero, después portugués/inglés |

---

## 3. Enfoque

### Stack Tecnológico

```
Capa             │ Tecnología
─────────────────┼─────────────────────────────
Backend API      │ FastAPI (Python 3.12+)
Base de datos    │ PostgreSQL + SQLAlchemy async
WhatsApp         │ Evolution API (self-hosted) 
IA               │ OpenAI GPT-4o-mini (vía API REST)
Calendario       │ Google Calendar API
Admin Panel      │ React + Tailwind (SPA)
Autenticación    │ JWT + magic links (email/WhatsApp)
Hosting          │ Railway / Render (escalado gradual)
Infraestructura  │ Docker + Docker Compose
```

### Arquitectura a Alto Nivel

```
┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   Paciente   │────▶│  Evolution  │────▶│  FastAPI     │
│  (WhatsApp)  │     │  API (WS)   │     │  (Webhook)   │
└──────────────┘     └─────────────┘     └──────┬───────┘
                                                │
┌──────────────┐     ┌─────────────┐           │
│  Administra  │────▶│  React SPA  │           │
│  (Web)       │     │  (Panel)    │           │
└──────────────┘     └─────────────┘           │
                                                ▼
                                        ┌──────────────┐
                                        │  PostgreSQL   │
                                        │  (Multi-      │
                                        │   tenant)     │
                                        └──────┬───────┘
                                               │
                                        ┌──────▼───────┐
                                        │  OpenAI API   │
                                        │  (GPT-4o-mini)│
                                        └──────────────┘
```

### Multi-tenencia

Estrategia: **tenant_id column** en todas las tablas (no esquemas separados). Es más simple al principio y se puede migrar a esquemas si un cliente requiere aislamiento fuerte.

### Flujo de Conversación Típico

1. Paciente escribe a WhatsApp de la clínica
2. Evolution API recibe el mensaje y lo envía como webhook a FastAPI
3. FastAPI identifica el tenant por el número de WhatsApp
4. El orquestador de IA clasifica la intención del mensaje (agendar, consultar FAQ, cancelar, etc.)
5. Según la intención, ejecuta la acción correspondiente (consultar Google Calendar, buscar en FAQ, etc.)
6. Genera respuesta con GPT-4o-mini + contexto recuperado
7. Envía respuesta vía Evolution API
8. Si no puede resolver o el paciente lo pide, deriva al panel de recepción

---

## 4. Riesgos y Mitigaciones

| Riesgo | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Costos de OpenAI se disparen | Medio | Baja | Cache de respuestas frecuentes, rate limiting, monitoreo |
| WhatsApp bloquee el número | Alto | Baja | Usar API oficial de Evolution, no enviar spam, mantener número templado |
| Clínicas no entienden la propuesta de valor | Alto | Media | Landing page clara, video de 2 min, onboarding guiado |
| Competidores bajan precios | Medio | Media | Diferenciarse en simpleza, soporte humano, no competir solo en precio |
| Alucinaciones del LLM en contexto médico | Alto | Media | Guardrails, prompt engineering, derivación a humano en caso de duda |
| Latencia de respuesta | Medio | Baja | Usar GPT-4o-mini (rápido), respuestas en caché para FAQs |

---

## 5. Criterios de Éxito

El MVP está completo cuando:

1. ✅ Una clínica real puede configurarse en < 30 minutos
2. ✅ Un paciente puede agendar un turno por WhatsApp sin intervención humana
3. ✅ El paciente recibe recordatorio 24h antes y puede confirmar/cancelar
4. ✅ El bot responde FAQs correctamente
5. ✅ Las conversaciones que el bot no puede resolver llegan al panel de recepción
6. ✅ El administrador ve todos los turnos y conversaciones desde el panel
7. ✅ Los turnos se sincronizan con Google Calendar del médico

---

## 6. Timeline Estimado

| Fase | Duración | Entrega |
|---|---|---|
| Especificaciones | 1 semana | Spec detallado |
| Diseño técnico | 1 semana | Arquitectura, DB, API design |
| Implementación MVP | 4-5 semanas | Código funcional |
| Testing y ajustes | 1 semana | Bugs pulidos |
| **Total MVP** | **~8 semanas** | Producto desplegable |

---

*Próximo paso: Pasar a especificaciones detalladas (spec)*
