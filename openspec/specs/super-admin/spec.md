# Super Admin Specification

## Purpose

Cross-tenant management dashboard for the SaaS owner — monitor, suspend, activate, and override subscription states across clinic tenants.

## Requirements

### Requirement: Super Admin Auth

Dashboard SHALL be accessible only to `role=super_admin`. A super admin MUST be seeded on deploy via env vars.

#### Scenario: Super admin logs in

- GIVEN `role=super_admin`
- WHEN logging in
- THEN `/admin/*` accessible, "Admin" nav link shown

#### Scenario: Clinic user denied

- GIVEN `role=admin` (clinic)
- WHEN navigating to `/admin`
- THEN 403

### Requirement: Tenant Overview

Dashboard MUST list all tenants (name, plan, status, trial end, subscription state) with filtering by plan and status.

#### Scenario: Filter suspended tenants

- GIVEN a super admin on the dashboard
- WHEN selecting "suspended" filter
- THEN only suspended tenants are shown

### Requirement: Tenant Status Management

Super admins MUST manually suspend/activate tenants. Activation MAY set a trial extension or manual subscription.

#### Scenario: Activate suspended tenant

- GIVEN a suspended tenant
- WHEN admin activates with 7-day extension
- THEN status becomes `active`, trial extended 7 days

### Requirement: Subscription Override

Super admins SHALL mark tenants as paid without MP. A note MUST record the reason.

#### Scenario: Manual payment

- GIVEN a suspended tenant
- WHEN admin selects "Mark as paid (manual)" with note
- THEN status becomes `active`, plan `subscription`, override badge shown
