# Subscription Billing Specification

## Purpose

Manage MP Checkout Pro subscription lifecycle — 7-day trial, recurring payments, webhook-driven lifecycle, billing UI for clinic tenants.

## Requirements

### Requirement: Free Trial on Registration

New tenants MUST start with `plan=trial, status=active, trial_ends_at = now + 7 days`.

#### Scenario: Standard registration

- GIVEN a registration request
- WHEN the tenant is created
- THEN plan is `trial`, status `active`, trial expiry 7 days out

#### Scenario: Past-due trial

- GIVEN `trial_ends_at` is already past at creation
- THEN status MUST be `suspended`

### Requirement: Checkout Preference

`POST /billing/checkout` MUST return an MP monthly subscription URL with `auto_return`, `back_urls`, and `notification_url`.

#### Scenario: Tenant starts checkout

- GIVEN a tenant with trial or suspended status
- WHEN POST /billing/checkout succeeds
- THEN an MP preference ID and URL are returned

#### Scenario: Already subscribed

- GIVEN a tenant with `status=active`
- WHEN POST /billing/checkout is called
- THEN 409 Conflict is returned

### Requirement: Webhook Processing

`POST /api/webhooks/mercadopago` MUST process MP events. `payment.approved`/`subscription_authorized` → `plan=subscription, status=active`. `payment.refunded`/`subscription_cancelled` → `status=suspended`.

#### Scenario: Payment approved

- GIVEN an MP webhook with `type=payment.approved` and valid signature
- WHEN processed
- THEN tenant becomes `subscription, active`

#### Scenario: Invalid signature

- GIVEN a webhook without valid MP signature
- WHEN received
- THEN 401, no data modified

### Requirement: Subscription Guard

Non-billing routes SHALL be blocked when `trial_ends_at < now AND status != active`. Guard MUST allow `/settings/billing`, `/api/webhooks/*`, `/admin/*`.

#### Scenario: Expired trial blocked

- GIVEN expired trial, status `suspended`
- WHEN accessing a restricted route
- THEN 402 Payment Required

#### Scenario: Billing UI exempt

- GIVEN a suspended tenant
- WHEN accessing `/settings/billing`
- THEN the request succeeds

### Requirement: Trial Expiry Scheduler

A Celery daily task MUST find tenants with `trial_ends_at < now AND status = active`, set `status = suspended`, and log each suspension.

#### Scenario: Trial ends

- GIVEN a tenant whose trial ended with `status=active`
- WHEN the daily task runs
- THEN status becomes `suspended` and an audit entry is created

### Requirement: Billing Settings UI

Settings > Billing SHALL show plan, status, trial end, "Subscribe" (if not active), and "Cancel" (if active). It SHOULD poll after MP checkout return.

#### Scenario: Tenant on trial

- GIVEN a tenant with 3 trial days left
- WHEN viewing Settings > Billing
- THEN remaining days and "Subscribe" are shown

#### Scenario: Tenant cancels

- GIVEN a tenant with `status=active`
- WHEN clicking "Cancel"
- THEN status becomes `suspended, plan=cancelled` and "Subscribe" appears
