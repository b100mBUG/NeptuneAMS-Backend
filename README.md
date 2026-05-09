# Attendance API (multi-tenant)

FastAPI backend for **many schools** on one deployment: platform provisioning, per-school admins/teachers, **multi-class teachers**, attendance by calendar date, CSV/PDF reports, and bulk student import (JSON, CSV, Excel).

## Stack

- FastAPI, Pydantic v2, `pydantic-settings`
- SQLAlchemy 2 async, PostgreSQL (`asyncpg`) or SQLite (`aiosqlite`)
- JWT (HS256), bcrypt, SlowAPI rate limits

## Quick start

```bash
cd Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set PLATFORM_SECRET, SECRET_KEY; for local DB bootstrap either DEBUG=true or MIGRATE_ON_START=true
python -m uvicorn main:app --reload
```

Or use the helper script (always uses `.venv`):

```bash
cd Backend
chmod +x run_dev.sh   # once
./run_dev.sh
```

**Why `ModuleNotFoundError` for `slowapi`?** The bare `uvicorn` command (often via `~/.pyenv/shims/uvicorn`) can run a **different** Python than the environment where you ran `pip install`. `pip list` then shows packages for that other env. Fix: activate the venv and run **`python -m uvicorn main:app`**, or **`./run_dev.sh`**.

Open `/docs` for interactive API.

### Platform (super admin)

1. `POST /platform/auth` with JSON `{ "platform_secret": "..." }` → JWT (`role`: `platform`).
2. `POST /platform/schools` with **Bearer** platform token creates a **school** and the **first admin** (no secret in body).
3. `GET /platform/schools` lists tenants with counts; `PATCH /platform/schools/{id}/active` sets `is_active` (offboard / re-enable). Inactive schools cannot log in (`school_slug` lookup requires active).

### Login

`POST /auth/login` JSON body:

```json
{
  "email": "admin@school.org",
  "password": "...",
  "school_slug": "westbury-high"
}
```

Response includes `access_token`, `role`, `school_id`, `school_slug`, `school_name`. All tenant-scoped requests resolve the school from the JWT (do not trust client-supplied school ids).

### Breaking changes from v2 (single-school)

- Login **must** include `school_slug` (emails can repeat across schools).
- Teachers use **`class_ids`** (many-to-many), not a single `c_id`.
- `POST /attendance/` requires **`class_id`** in the body for authorization.
- Students are unique per school by admission id **`(school_id, id)`**; paths unchanged (`/classes/{class_id}/students/{student_id}`).
- Attendance rows use **`session_date`** (calendar day) and support **`excused`**, **`note`**, **`marked_by_teacher_id`**.

## Notable endpoints

| Area | Methods | Notes |
|------|---------|--------|
| Platform | `POST /platform/schools` | Provision tenant + bootstrap admin |
| Auth | `POST /auth/login`, `POST /auth/teacher/register`, `POST /auth/admin/register` | Admin adds more admins for same school |
| School | `GET /schools/me` | Current tenant + role |
| Classes | `GET/POST /classes/`, `GET /classes/search`, teachers per class `GET /classes/{id}/teachers` | Paginated lists |
| Teachers | `GET /teachers/me`, `PATCH /teachers/{id}/classes` | Multi-class assignment |
| Students | `POST .../import`, `POST .../import-file` | JSON array or `.csv` / `.xlsx` |
| Attendance | `POST /attendance/`, summaries, class roll | Teacher must be assigned to class |
| Reports | `GET /reports/classes/{id}/attendance.csv`, `.pdf` | Admin-only; date range |

## Environment

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | e.g. `postgresql+asyncpg://user:pass@host/db` or SQLite URL |
| `SECRET_KEY` | JWT signing; min 8 chars if `DEBUG=false` |
| `PLATFORM_SECRET` | Required to call `/platform/schools` |
| `DEBUG` | `true` → auto `create_all` on startup (dev only) |
| `MIGRATE_ON_START` | `true` → run `create_all` (emergency bootstrap; prefer Alembic in production) |
| `CORS_ORIGINS` | Comma-separated origins |
| `RATE_LIMIT_*` | SlowAPI limits |

## Production notes

- Turn off `DEBUG` and `MIGRATE_ON_START`; use **Alembic** migrations and manage schema explicitly.
- Use a strong `SECRET_KEY` and HTTPS.
- PostgreSQL is recommended beyond small pilots.

## What schools typically expect (product checklist)

Use this as a roadmap beyond the API:

- **Registers**: AM/PM or per-period; optional lesson/timetable later.
- **Statuses**: present, absent, late, **excused**; notes on entries.
- **Roles**: tenant admin, teacher (multi-class), optional read-only/report roles later.
- **Rosters**: bulk import, per-school admission ids, soft delete, restore.
- **Reporting**: exports (CSV/PDF), date ranges, class and student summaries.
- **Compliance**: audit who marked attendance (`marked_by_teacher_id`), data residency, export/delete story (extend with dedicated audit tables as needed).
