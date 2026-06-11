# Proposal: SaaS Subscription Billing

## Intent

Clinics use the chatbot free indefinitely — no revenue model exists. Add Mercado Pago billing with a 7-day trial, then require monthly subscription per clinic.

## Scope

**In**: MP Checkout Pro, Tenant MP fields + trial, 7d trial on register, subscription guard, billing Settings tab, super admin panel, Celery trial expiry + sub sync, MP webhooks
**Out**: Tiered/usage-based pricing, invoices, proration, free plan, multi-currency

## Capabilities

**New**: `subscription-billing` (MP checkout, webhooks, lifecycle, billing UI), `super-admin` (cross-tenant dashboard)
**Modified**: None

## Approach

1. Add `mercadopago` SDK + config
2. Extend `Tenant`: MP fields, add `free_trial`/`cancelled` to plan enum
3. Register → tenant with 7d trial
4. `SubscriptionGuard` dep — blocks non-billing routes if trial expired + no sub
5. `POST /billing/checkout` → MP preference
6. Webhook `/api/webhooks/mercadopago` → sub status updates
7. "Facturación" tab → status, subscribe, cancel
8. `/admin/*` + super admin UI
9. Celery daily: trial expiry check

## Affected Areas

| Area | Impact | |
|------|--------|-|
| `models/tenant.py` | Mod | MP fields, trial dates, plan enum |
| `api/auth.py` | Mod | Trial tenant on register |
| `api/deps.py` | Mod | Subscription guard |
| `api/billing.py` | New | MP checkout + webhooks |
| `api/admin.py` | New | Super admin |
| `core/config.py` | Mod | MP credentials |
| `scheduler/tasks.py` | New | Trial expiry |
| `requirements.txt` | Mod | `mercadopago` |
| `frontend/Settings.tsx` | Mod | Billing tab |
| `frontend/Admin.tsx` | New | Super admin UI |
| `frontend/AuthContext.tsx` | Mod | Tenant plan/status |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| MP webhook delivery failure | Low | Retry + manual super admin sync |
| Clinic loses access mid-cycle | Low | Suspended tenants keep /settings/billing |
| MP SDK version conflicts | Low | Pin version, test in staging |

## Rollback Plan

1. Alembic downgrade to remove MP fields
2. Remove subscription guard from deps
3. Revert register to `plan=free, status=active`
4. Remove billing + admin endpoints + SDK
5. Frontend: revert Settings, remove Admin page

## Dependencies

- `mercadopago` SDK
- MP API credentials (access token, webhook secret)

## Success Criteria

- [ ] New clinic blocked after 7d trial without subscription
- [ ] Clinic completes MP checkout → subscription active
- [ ] Webhook updates tenant status on MP events
- [ ] Super admin sees/manages all tenants
- [ ] Celery daily task suspends expired trials
