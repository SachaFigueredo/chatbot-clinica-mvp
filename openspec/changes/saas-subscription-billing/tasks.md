# Tasks: SaaS Subscription Billing

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900–1100 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend foundation: enums, model, migration, config, grandfather, SubscriptionGuard, register trial, Celery task | PR 1 | base=main |
| 2 | Backend billing: billing.py, webhooks, admin.py, main.py registration | PR 2 | base=main |
| 3 | Frontend: api.ts types, BillingSettings, Admin page, routes, AuthContext | PR 3 | base=main |

## Phase 1: Foundation

- [x] 1.1 Extend `enums.py`: `TenantPlan` (+trial,subscription,cancelled), `UserRole` (+super_admin)
- [x] 1.2 Add `trial_ends_at`, `mercadopago_customer_id`, `mercadopago_subscription_id`, `suspended_at` to `Tenant` model
- [x] 1.3 Create Alembic migration (nullable cols, no default)
- [x] 1.4 Add MP config vars + super admin seed vars to `config.py`
- [x] 1.5 Data migration: existing tenants → `plan=subscription`, `status=active` (grandfather)
- [x] 1.6 Modify `auth.py` register: new tenant → `plan=trial`, `trial_ends_at=now+7d`

## Phase 2: Guard & Dependencies

- [x] 2.1 Add `SubscriptionGuard` dep in `deps.py`: blocks if trial expired, exempts /billing/* and /webhooks/*
- [x] 2.2 Add `CurrentSuperAdmin` dep: checks `role=super_admin` or 403
- [x] 2.3 Wire `SubscriptionGuard` into non-billing/non-auth/non-webhook routers in `main.py`

## Phase 3: Billing API

- [x] 3.1 Create `billing.py`: `POST /checkout`, `GET /status`, `POST /cancel`
- [x] 3.2 Create `webhooks/mercadopago.py`: signature verify + event processing
- [x] 3.3 Create `admin.py`: `GET /tenants`, suspend/activate/mark-paid
- [x] 3.4 Register billing, admin, webhook routers in `main.py`

## Phase 4: Celery Task

- [x] 4.1 Create `tasks/trial_expiry.py`: find expired trials → suspend + log
- [x] 4.2 Add daily `check-trial-expiry` beat schedule to `celery_app.py`

## Phase 5: Frontend

- [x] 5.1 Add billing + admin types and service objects to `api.ts`
- [x] 5.2 Create `BillingSettings.tsx`: plan/status/trial days, Subscribe/Cancel
- [x] 5.3 Add "Facturación" tab in `Settings.tsx`
- [x] 5.4 Create `Admin.tsx`: tenant list table with suspend/activate
- [x] 5.5 Add `/admin` route in `App.tsx` inside Layout
- [x] 5.6 Add "Admin" nav link for `super_admin` in `Layout.tsx`
- [x] 5.7 Expose tenant plan/status/trial_ends_at in `AuthContext.tsx`

## Phase 6: Tests

- [x] 6.1 Unit: SubscriptionGuard — active allows, expired blocks, billing exempt
- [x] 6.2 Unit: Trial expiry task — mock query, assert suspension
- [x] 6.3 Integration: Register → trial tenant (plan=trial, +7d)
- [x] 6.4 Integration: /billing/checkout with active sub → 409
- [x] 6.5 Integration: Webhook invalid signature → 401, no DB change
- [x] 6.6 Integration: Admin without super_admin → 403
