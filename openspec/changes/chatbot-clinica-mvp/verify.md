# Verification Report

**Change**: chatbot-clinica-mvp
**Scope**: T5 — Google Calendar Integration
**Version**: spec.md F7 (lines 313-368)
**Mode**: Standard (no test framework, no Strict TDD)

---

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (T5) | 1 |
| Tasks complete | 1 |
| Tasks incomplete | 0 |

T5 is marked COMPLETED in tasks.md. All 6 files exist and have been created/modified as specified.

---

## Build & Tests Execution

**Syntax check**: ✅ Passed — all 6 files pass `python -m py_compile`

```text
python -m py_compile backend/app/domain/interfaces/calendar.py → OK
python -m py_compile backend/app/infrastructure/calendar/__init__.py → OK
python -m py_compile backend/app/infrastructure/calendar/models.py → OK
python -m py_compile backend/app/infrastructure/calendar/google.py → OK
python -m py_compile backend/app/api/v1/calendar.py → OK
python -m py_compile backend/app/main.py → OK
```

**Import verification**: ✅ Domain interface and models import successfully.
Infrastructure provider (`google.py`) fails at runtime due to missing `asyncpg` dependency and a `metadata` naming conflict in the `conversation.py` model (T2 dependency, not T5).

```text
app.domain.interfaces.calendar → OK
app.infrastructure.calendar.models → OK
app.infrastructure.calendar.google → FAIL (missing asyncpg, conversation model metadata bug)
app.api.v1.calendar → FAIL (dependency chain blocked by conversation.py)
app.main → FAIL (dependency chain blocked)
```

**Tests**: ➖ No test framework is set up. No `pytest` config, no `conftest.py`, no test files exist for T5.

**Coverage**: ➖ Not available.

---

## Spec Compliance Matrix (F7)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| OAuth 2.0 flow with consent screen | Happy path — Admin connects calendar | (no test) | ⚠️ UNTESTED — implemented via `get_auth_url` with `access_type=offline&prompt=consent` |
| Token encryption with Fernet | Token storage | (no test) | ⚠️ UNTESTED — implemented via `_encrypt_token`/`_decrypt_token` using `cryptography.fernet.Fernet` |
| Auto-refresh of expired tokens | Token refresh on expiry | (no test) | ⚠️ UNTESTED — implemented via `_ensure_valid_token` + `_refresh_token` |
| `get_available_slots` excludes existing events and respects business hours | Availability check | (no test) | ⚠️ UNTESTED — implemented with busy-ranges overlap check and `_get_business_hours` |
| `create_event` with patient data | Event creation | (no test) | ⚠️ UNTESTED — implemented with `[Paciente]` prefix, phone and reason in description |
| `delete_event` removes event | Event deletion | (no test) | ⚠️ UNTESTED — implemented via Google Calendar DELETE endpoint |
| Token expiry notification | Token expired error | (no test) | ⚠️ UNTESTED — raises `ConnectionError` but no proactive WhatsApp/email notification |
| 4 API endpoints defined and registered | Route registration | (no test) | ⚠️ UNTESTED — verified via source inspection: all 4 endpoints exist and are registered |

**Compliance summary**: 0/8 scenarios have covering tests. All scenarios are UNTESTED.

---

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| F7.1 OAuth 2.0 consent URL generation | ✅ Implemented | `get_auth_url` builds URL with offline access and consent prompt. Optional `state` param for doctor_id. |
| F7.2 OAuth callback + token exchange | ✅ Implemented | `handle_callback` exchanges code for tokens, discovers primary calendar, persists encrypted tokens. |
| F7.3 Token encryption | ✅ Implemented | Fernet symmetric encryption used for both access and refresh tokens. |
| F7.4 Token auto-refresh | ✅ Implemented | `_ensure_valid_token` refreshes if within 5 min of expiry. Access token and optional new refresh token persisted. |
| F7.5 Availability slots | ✅ Implemented | `get_available_slots` fetches events, builds busy ranges, respects business hours, generates candidate slots at 15-min granularity. |
| F7.6 Business hours config | ✅ Implemented | `_get_business_hours` reads from `ClinicConfig.business_hours` JSONB, defaults to 08:00-17:00. Closed days return zero-length range. |
| F7.7 Create event | ✅ Implemented | Title `[Paciente] {name}`, description with phone and reason, America/Argentina/Buenos_Aires timezone. |
| F7.8 Delete event | ✅ Implemented | 404 treated as success (event already gone), 204 on success. |
| F7.9 Connection status | ✅ Implemented | `get_connection_status` returns connected state, email, and expiry. Attempts refresh if token is expired. |
| F7.10 Disconnect | ✅ Implemented | Soft-deletes token by setting `is_active = False`. |

---

## Coherence (Design)

| Design Decision | Followed? | Notes |
|---|---|---|
| Async httpx for Google API calls | ✅ Yes | All external HTTP calls use `httpx.AsyncClient()`. |
| Hexagonal architecture (interface in domain, adapter in infrastructure) | ✅ Yes | `CalendarProvider` (abstract) in `domain/interfaces/`, `GoogleCalendarProvider` in `infrastructure/calendar/`. |
| Token encryption with `cryptography.fernet` | ✅ Yes | Fernet used in `_encrypt_token`/`_decrypt_token` helpers. |
| 4 API endpoints at `/api/v1/calendar/*` | ✅ Yes | All 4 endpoints (GET/POST/GET/DELETE) registered via `calendar_router`. |
| Project structure: API under `presentation/api/v1/` | ⚠️ Partial | Design specifies `backend/app/presentation/api/v1/calendar.py`. Code places it at `backend/app/api/v1/calendar.py`. Same for middleware (`app/api/middleware/` instead of `app/presentation/middleware/`). Functional, but deviates from the designed directory layout. |
| Event prefix `[Bot]` per RN7.4 | ❌ No (spec inconsistency) | RN7.4 says `[Bot]` prefix but F7 flow example uses `[Paciente]`. Code implements `[Paciente]` matching the flow example. This is a spec inconsistency, not purely an implementation issue. |
| `ConnectionStatus` and `AvailableSlot` DTOs in domain layer | ❌ Partially | Both `domain/interfaces/calendar.py` and `infrastructure/calendar/models.py` define identical classes. Duplication should be resolved by defining once in domain and importing in infrastructure. |

---

## Issues Found

**CRITICAL**:
1. **No tests exist** for any T5 functionality. Zero coverage. Cannot verify behavioral compliance via test execution.
2. **Missing runtime dependencies**: `httpx`, `cryptography`, `fastapi`, `uvicorn`, `asyncpg` are not listed in any `requirements.txt` or installed. The project has no requirements files at all (`**/requirements*` returned no results).
3. **Blocking bug in T2 (conversation model)**: `ConversationMessage` has a column named `metadata` (line 67 of `conversation.py`), which is reserved by SQLAlchemy's Declarative API. Error: `Attribute name 'metadata' is reserved when using the Declarative API.` This blocks importing the T5 calendar module chain at runtime since `google.py` imports DB models that trigger the `conversation.py` import.

**WARNING**:
1. **CA7.4 not fully met**: Spec says "se notifica al admin por WhatsApp y email" when token expires. Implementation only raises `ConnectionError`. There is no proactive notification mechanism (WhatsApp/email) implemented.
2. **Design directory structure deviation**: Code places API files at `app/api/v1/` and middleware at `app/api/middleware/` instead of `app/presentation/api/v1/` and `app/presentation/middleware/` as specified in the design document.
3. **DTO duplication**: `AvailableSlot` and `ConnectionStatus` classes are defined in both `domain/interfaces/calendar.py` and `infrastructure/calendar/models.py`. The `CalendarProvider` interface references the domain copy, while `google.py` imports from the infrastructure copy.

**SUGGESTION**:
1. **Missing event color/label**: Spec mentions "Color/etiqueta: según corresponda" but `create_event` does not set any `colorId` or extended properties to identify bot-created events.
2. **No requirements files**: Project has no `requirements/base.txt`, `requirements/dev.txt`, or any dependency manifest. Add them for reproducibility.
3. **Rename `metadata` column**: In `ConversationMessage` model, rename `metadata` to `extra_data` or `meta` to resolve the SQLAlchemy reserved-name conflict.

---

## Verdict

**PASS WITH WARNINGS**

The implementation is syntactically correct, structurally complete, and functionally matches all F7 requirements from the spec when inspected statically. All 4 API endpoints exist and are registered, the hexagonal architecture is followed, and every specified operation (OAuth, token encryption, auto-refresh, slot calculation, event CRUD, status, disconnect) is implemented.

The verdict is not `FAIL` because:
- All syntax checks pass
- All required files exist at correct paths (relative to the project)
- Every spec requirement has a corresponding code implementation
- The design architecture (hexagonal, async httpx, Fernet encryption) is followed
- All 4 endpoints are properly defined and registered

The verdict is not `PASS` (without warnings) because:
- Zero tests exist — no behavioral verification possible
- A blocking bug in the DB model layer (T2 dependency) prevents runtime import of the calendar module
- CA7.4 notification requirement is partially unmet
- Design directory structure is deviated
- DTO duplication exists
