#!/bin/bash
set -e

# Cron jobs run with a minimal environment, so persist the container env to a
# file the jobs can source. %q quoting keeps connection strings with special
# characters intact. Written to /app (the /app/ingestion mount may be read-only).
env -0 | while IFS='=' read -r -d '' name value; do
  printf 'export %s=%q\n' "$name" "$value"
done > /app/cron.env
echo "Wrote runtime env to /app/cron.env"

crontab /app/ingestion/crontab
echo "Installed crontab:"
crontab -l

# Optionally run every job once at startup (handy for first-run / debugging).
if [ "${RUN_ON_START:-false}" = "true" ]; then
  echo "RUN_ON_START=true -> running all ingest jobs once..."
  # shellcheck disable=SC1091
  . /app/cron.env
  cd /app/ingestion
  for job in ingest_codebase ingest_database ingest_linear ingest_sentry ingest_slack ingest_gmail; do
    echo "--- running ${job} ---"
    python3 "${job}.py" || echo "${job} failed (continuing)"
  done
fi

echo "Starting cron in foreground..."
exec cron -f
