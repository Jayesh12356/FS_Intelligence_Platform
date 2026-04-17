# Alembic migrations

All schema changes MUST go through Alembic after the 0001 baseline.

## Workflow

```bash
cd backend
# autogenerate a new revision from diff between DB and Base.metadata
alembic revision --autogenerate -m "short description"

# apply
alembic upgrade head

# rollback one
alembic downgrade -1
```

## Startup behaviour

On app startup `app.db.init_db.init_db()` does, in order:

1. Run `Base.metadata.create_all` — creates any brand-new tables (safe idempotent).
2. Run `alembic upgrade head` — applies any pending migrations.
3. Stamps `0001_baseline` if the DB is old and has no `alembic_version` row.

This means fresh installs and existing DBs both land at `head` without manual steps.
