# ---- Development stage ----
FROM python:3.12-slim AS dev

WORKDIR /app

COPY requirements/base.txt requirements/dev.txt /app/requirements/
RUN pip install --no-cache-dir -r requirements/dev.txt

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- Production stage ----
FROM python:3.12-slim AS prod

WORKDIR /app

COPY requirements/base.txt /app/requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY alembic/ alembic/
COPY alembic.ini .
COPY app/ app/
COPY tasks/ tasks/

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
