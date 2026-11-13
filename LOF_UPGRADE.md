# LOF fork — upgrade from Horilla 1.x to 2.4.0

This folder is upstream **Horilla HR 2.4.0** with the LOF/TRG customisations from
the 1.x fork (`../`, the old `Horilla-Trg-main`) carried over. The old folder is
left untouched as a fallback.

## Where the LOF code lives now

| LOF feature | 1.x location | 2.4.0 location |
|---|---|---|
| Portal SSO (`/sso/?lof_token=`), `/login/` → portal | `horilla/lof_backend.py`, `lof_sso_view.py`, patched `settings.py`/`urls.py` | same `horilla/lof_*.py`; settings in `horilla/settings/local_settings.py`; 3 routes at top of `horilla/urls.py` |
| App-switcher context (PORTAL_URL, …) | `horilla/lof_context.py` via `horilla_context_processors.py` | `horilla/lof_context.py`, registered in `local_settings.py` |
| `hr` schema `search_path`, `FORCE_SCRIPT_NAME` | `horilla/settings.py` | `local_settings.py` |
| Travel & Expense app | `travel/` | `travel/` (registration updated for 2.x) |
| LOF App Switcher in navbar | `templates/index.html` | `lof_integration/templates/lof/app_switcher.html`, included from `horilla_theme/templates/horilla_theme/components/header.html` |
| LOF blue brand colour | `static/css/lof-theme.css` | DB colour theme — run `python manage.py setup_lof_theme` |
| Payroll Flow page | `payroll/views/views.py`, `payroll/templates/payroll/flow.html` | `lof_integration/views.py`, `lof_integration/templates/payroll/lof_flow.html`; menu entry in `payroll/sidebar.py` |
| eSSL biometric fixes | `biometric/views.py` | `biometric/views.py` (marked `LOF:`) |
| eSSL / reconciliation ops scripts | repo root `*.py` | `scripts/lof_ops/` |

Upstream files touched (keep this list in mind on the next upstream upgrade):
`horilla/urls.py`, `horilla/settings/local_settings.py`, `biometric/views.py`,
`payroll/sidebar.py`, `horilla_theme/templates/horilla_theme/components/header.html`,
`.env.dist`, `.gitignore`.

## Fixes made while porting

- **Travel approvals crashed on every request** — `approval, _ = get_or_create(...)`
  shadowed gettext `_` inside the view (`UnboundLocalError`). Renamed to `_created`.
- **Travel notifications were never delivered** — rows were created without the
  required actor and the error was swallowed. Now uses Horilla's `notify.send`.
- Travel notifications and the Travel Desk agent call now fire **after the DB
  commit**; the agent call sends `Authorization: Bearer $PLATFORM_AGENT_TOKEN` if set.
- **SSO open redirect** — `/sso/?next=` now only accepts same-site URLs.
- **Biometric sync** — fetch markers are saved *after* punches are processed (a
  crash no longer silently skips punches), newest punch is found with `max()`,
  and punch code 255 alternates in/out (legacy eSSL firmware).
- `scripts/lof_ops/fix_and_resync.py` uses `get_user_model()` (2.x has a custom
  user model). Scripts resolve the project root from their new folder.

## Database — read before pointing 2.4.0 at the live DB

2.4.0 is **not** a drop-in on the 1.x database:

- 1.x never committed migrations; the live DB's `django_migrations` holds
  locally generated ones (`0001_initial`, …). 2.4.0 ships its *own* migrations
  with the same names but different contents, so `migrate` would wrongly treat
  them as applied and leave the schema mismatched.
- 2.x uses a custom user model (`horilla_auth.HorillaUser`) instead of `auth.User`.
  Upstream's `python manage.py migrateusers` copies users, groups and
  permissions from the old `auth_user` tables.
- Django moved from 4.2 to 5.2.

Recommended path:

1. **Back up** the live DB (`pg_dump`) and the `media/` folder.
2. Create a **new, empty schema/database** for 2.4.0 (e.g. schema `hr2`, set
   `DB_SEARCH_PATH_OPTIONS=-c search_path=hr2,public`), then:
   ```
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py setup_lof_theme
   python manage.py collectstatic --noinput
   ```
3. Bring the data across. Users come over through `migrateusers` when the old
   `auth_user` table is reachable on the same search_path. Employees and other
   master data can use the new `master_import` app (Excel). Attendance can be
   pulled again from the eSSL device with the backfill scripts in
   `scripts/lof_ops/`.
4. Test SSO from the portal against the new instance, then switch nginx `/hr`
   over to it.

Do a trial run on a copy of the database first.
