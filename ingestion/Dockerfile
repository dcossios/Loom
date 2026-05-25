FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/ingestion

RUN pip install --no-cache-dir \
    "requests>=2.31" \
    "sqlalchemy>=2.0,<3" \
    "psycopg2-binary>=2.9" \
    "pymysql>=1.1"

COPY . /app/ingestion

# Invoke via bash so a read-only bind mount over /app/ingestion (without the
# executable bit) still starts.
ENTRYPOINT ["bash", "/app/ingestion/entrypoint.sh"]
