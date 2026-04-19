FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create uploads directory
RUN mkdir -p /app/uploads

EXPOSE 8000

# The FastAPI lifespan in app.main calls ``app.db.init_db.init_db`` on
# startup which (1) creates tables from Base.metadata for fresh installs,
# (2) stamps the Alembic baseline if a legacy DB lacks alembic_version,
# and (3) runs ``alembic upgrade head``. We must NOT run alembic directly
# before the lifespan hook, or migration ``0002_ambiguity_resolution_text``
# will ALTER a table before step (1) has a chance to create it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
