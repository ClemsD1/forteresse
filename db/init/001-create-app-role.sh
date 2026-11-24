#!/bin/sh
set -eu

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 \
  --set=app_user="$APP_DB_USER" \
  --set=app_password="$APP_DB_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE',
  :'app_user',
  :'app_password'
)
\gexec

GRANT USAGE ON SCHEMA public TO :"app_user";
GRANT CREATE ON SCHEMA public TO :"app_user";
ALTER DEFAULT PRIVILEGES
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";
SQL

@main_bp.get("/demo-erreur")
def demo_error():
    raise RuntimeError("Détail de test visible dans le journal")
