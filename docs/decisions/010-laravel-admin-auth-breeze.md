# ADR-010 — Laravel Admin Panel Auth: Laravel Breeze

## Context

Adding a Laravel admin panel service to the monorepo. Needed an auth strategy for the admin UI. Three options considered.

## Options Considered

**Option A — Laravel Breeze (email + password)**
Admins stored in a dedicated `admins` table in Aurora. Laravel handles sessions natively.
- Rejected cons: credentials siloed from Cognito User Pool.

**Option B — Cognito SSO via Laravel Socialite**
Admin panel acts as OAuth2 client against existing Cognito User Pool.
- Rejected: high local setup friction (App Clients, redirect URLs, AWS credentials); adds infra coupling for a didactic service.

**Option C — No auth (VPC-only)**
App is open; network perimeter provides security.
- Rejected: zero audit trail; misconfigured SG exposes panel publicly.

## Decision

**Laravel Breeze (Option A).**

Local dev works offline with zero AWS config. Native Laravel auth is the focus of the learning goal — sessions, guards, middleware are all Laravel-specific primitives worth understanding firsthand.

## Usage

```bash
composer require laravel/breeze --dev
php artisan breeze:install blade
php artisan migrate
```

Admins managed via `admins` table (separate from end-user `subscriptions`). Laravel default `users` table renamed or guarded to avoid confusion with Cognito-managed end users.

## Consequences

- Admin credentials live in Aurora alongside newsletter data — same DB, separate table.
- No SSO: if a Cognito user needs admin access, credentials must be created separately in the `admins` table.
- Upgrade path: swap Breeze guard for Socialite + Cognito provider later without touching Filament resource code.
