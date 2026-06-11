# Design: SaaS Subscription Billing

## Technical Approach

Extend Tenant model with Mercado Pago billing fields, set 7-day trial on registration, enforce subscription via a per-route FastAPI dependency. MP Checkout Pro subscriptions for recurring billing. Celery daily task for trial expiry. Super admin endpoints for cross-tenant management.

## Architecture Decisions

| Decision | Options | Tradeoffs | Choice |
|----------|---------|-----------|--------|
| Guard placement | Middleware vs Dependency | Middleware needs fragile path-exclusion; dependency follows existing `deps.py` pattern and naturally skips public webhooks | **`SubscriptionGuard` dependency** in `deps.py` |
| Suspended billing access | Path check vs separate router | Path check couples guard to URL structure. Separate `/billing` router with no guard is simpler. | **`/api/v1/billing/*` is exempt** — its router never uses the guard |
| Trial tracking | `created_at + 7d` vs explicit column | Column is queryable — Celery finds expired trials with `WHERE trial_ends_at < now()` without joins | **`trial_ends_at` column** — `DateTime(timezone=True)` |
| Payment model | Subscription vs One-time | Subscriptions auto-renew monthly. Spec requires "monthly subscription." | **MP Subscription** via Checkout Pro |
| Webhook auth | Signature verification | MP sends `X-Signature` HMAC-SHA256. Verify in a lightweight dependency before processing. | **`verify_mp_webhook` dep** in webhooks router |
| Super admin auth | Role check in deps | Extend `UserRole` with `super_admin`, seed via env. Reuse pattern from `CurrentUser`. | **`CurrentSuperAdmin`** dependency |

## Data Flow

```
Register → Tenant(trial, 7d)
  ├─ Pays within 7d → POST /billing/checkout → MP preference
  │    → User pays in MP → Webhook: subscription_authorized
  │    → Tenant(status=active, plan=subscription)
  └─ Trial expires → Celery daily → status=suspended
       → Guard blocks all API except /billing/* and /admin/*
       → Billing UI still shows "Subscribe" button
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `models/tenant.py` | Modify | Add `trial_ends_at`, `mercadopago_customer_id`, `mercadopago_subscription_id`, `suspended_at` |
| `domain/enums.py` | Modify | Add `trial`, `subscription`, `cancelled` to `TenantPlan`; add `super_admin` to `UserRole` |
| `api/deps.py` | Modify | Add `SubscriptionGuard` + `CurrentSuperAdmin` dependencies |
| `api/v1/auth.py` | Modify | Registration sets `plan=trial, trial_ends_at=now+7d` |
| `api/v1/billing.py` | Create | `POST /checkout`, `GET /status`, `POST /cancel` |
| `api/v1/admin.py` | Create | `GET /tenants`, `GET /tenants/{id}`, `POST /tenants/{id}/suspend`, `POST /tenants/{id}/activate`, `POST /tenants/{id}/mark-paid` |
| `api/v1/webhooks/mercadopago.py` | Create | `POST /mercadopago` — process MP subscription events |
| `config.py` | Modify | Add `mp_access_token`, `mp_webhook_secret`, `mp_notification_url`, `super_admin_email`, `super_admin_password` |
| `tasks/trial_expiry.py` | Create | Find `trial_ends_at < now AND status=active`, set `status=suspended`, log |
| `tasks/celery_app.py` | Modify | Add `check-trial-expiry` daily beat schedule |
| `main.py` | Modify | Register `billing`, `admin`, `webhooks/mercadopago` routers |
| `Settings.tsx` | Modify | Add "Facturación" tab rendering `BillingSettings` component |
| `api.ts` | Modify | Add `billing.*` and `admin.*` service objects |
| `App.tsx` | Modify | Add `/admin` route with `SuperAdmin` guard |
| `Layout.tsx` | Modify | Add "Admin" nav link for `super_admin` role |
| `AuthContext.tsx` | Modify | Expose `tenant` (plan, status, trial_ends_at) in user context |

## Interfaces / Contracts

```python
# Tenant model additions
trial_ends_at: datetime | None
mercadopago_customer_id: str | None
mercadopago_subscription_id: str | None
suspended_at: datetime | None

# SubscriptionGuard usage
router = APIRouter(dependencies=[Depends(SubscriptionGuard)])

# API
POST /api/v1/billing/checkout → { preference_id, init_point }
GET  /api/v1/billing/status   → { plan, status, trial_ends_at, days_remaining }
POST /api/v1/billing/cancel   → { status: "cancelled" }
POST /api/v1/webhooks/mercadopago → { status: "ok" }
GET  /api/v1/admin/tenants?status=&plan= → [TenantListItem]
POST /api/v1/admin/tenants/{id}/suspend  → { status: "suspended" }
POST /api/v1/admin/tenants/{id}/activate → { status: "active", trial_ends_at }
POST /api/v1/admin/tenants/{id}/mark-paid → { plan: "subscription", status: "active" }
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | BillingService.create_preference | Mock MP SDK, assert correct payload |
| Unit | SubscriptionGuard logic | Test active/trial/suspended/expired cases |
| Unit | Trial expiry task | Mock query, assert status updates |
| Integration | Register→trial tenant | httpx AsyncClient, check DB |
| Integration | /billing/checkout with active sub | Expect 409 |
| Integration | Webhook invalid signature | Expect 401, no DB change |
| Integration | Admin endpoints without super_admin | Expect 403 |

## Migration / Rollout

1. Alembic: add nullable columns to `tenants` table
2. Data migration: existing tenants → `plan=subscription`, `status=active` (grandfather)
3. Super admin: seed on first deploy via `SUPER_ADMIN_EMAIL` + `SUPER_ADMIN_PASSWORD` env
4. Deploy backend first, then frontend
5. Configure MP webhook URL in MP panel (use ngrok for local dev)

## Open Questions

- [ ] Existing `plan=free` tenants — grandfather as subscription or give 7-day trial?
- [ ] MP webhook secret — delivered via env var or configured in MP panel?
- [ ] Should we add a trial extension endpoint for super admin to grant extra days?
