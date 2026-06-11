# Apply Progress — SaaS Subscription Billing (PR 3)

## Summary

Implemented Phase 5 (Frontend) for the SaaS subscription billing change. All 7 frontend tasks complete. Build passes with zero TypeScript errors.

## Chain Strategy

stacked-to-main — PR 3, base=main (PRs 1 and 2 already merged).

## Files Created (this batch)

| File | Description |
|------|-------------|
| `frontend/src/pages/BillingSettings.tsx` | Subscription plan/status display, trial countdown, Subscribe/Cancel buttons |
| `frontend/src/pages/Admin.tsx` | Super admin tenant list table with suspend/activate/mark-paid actions |
| `frontend/src/components/SuperAdminRoute.tsx` | Route guard for super_admin role |

## Files Modified (this batch)

| File | Description |
|------|-------------|
| `frontend/src/services/api.ts` | Added `plan`, `status`, `trial_ends_at` to `User`; added `super_admin` to role union; added `BillingStatus`, `CheckoutResponse`, `TenantAdmin`, `AdminTenantsParams` types; added `billing` and `admin` service objects |
| `frontend/src/pages/Settings.tsx` | Added "Facturación" tab with `CreditCard` icon, renders `BillingSettings` component |
| `frontend/src/App.tsx` | Added `/admin` route wrapped in `SuperAdminRoute` inside Layout |
| `frontend/src/components/Layout.tsx` | Added "Admin" nav link with `Shield` icon, visible only for `super_admin` role |

## Previous Progress (PR 2) — Preserved

### Files Created (PR 2)
| File | Lines | Description |
|------|-------|-------------|
| `app/domain/services/billing_service.py` | 148 | Mercado Pago billing service |
| `app/api/v1/billing.py` | 140 | Billing endpoints |
| `app/api/v1/webhooks/mercadopago.py` | 140 | MP webhook handler |
| `app/api/v1/admin.py` | 174 | Super admin endpoints |

### Files Modified (PR 2)
| File | Lines | Description |
|------|-------|-------------|
| `app/main.py` | +8 | Registered billing, admin, mercadopago webhook routers |
| `tests/conftest.py` | +3 | Added MP test env vars |

## Test Results (PR 2 preserved)
**192 passed**, 1 warning, 0 failures.

## Deviations from Design

- **Admin route guard**: Used a dedicated `SuperAdminRoute` component (wraps `<Outlet />`) instead of a more complex approach. This is consistent with the existing `ProtectedRoute` pattern in the codebase and matches the design intent.
- **Nav item for Admin**: Added `superAdminOnly` field to `NavItem` interface in Layout. The existing `adminOnly` filter was updated to also include `super_admin` (since super_admin has all admin privileges), and `superAdminOnly` items are only shown to `super_admin`.

## Issues Found

None.

## Remaining Tasks

None. All Phase 5 tasks are complete.

## Status

All 7 tasks complete. Ready for verify phase.
