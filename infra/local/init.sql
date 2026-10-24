-- Local dev only: extensions, schemas, roles (password = role name). Cloud uses cm-migrate instead.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
DO $$ BEGIN
  IF (SELECT string_to_array(extversion, '.')::int[] FROM pg_extension WHERE extname = 'vector') < '{0,7,0}'::int[]
  THEN RAISE EXCEPTION 'pgvector >= 0.7 required for halfvec'; END IF;
END $$;
CREATE ROLE cm_admin  LOGIN PASSWORD 'cm_admin' CREATEROLE;
CREATE ROLE cm_app    LOGIN PASSWORD 'cm_app';
CREATE ROLE cm_engine LOGIN PASSWORD 'cm_engine';
CREATE ROLE cm_reader LOGIN PASSWORD 'cm_reader';
CREATE SCHEMA IF NOT EXISTS cm AUTHORIZATION cm_admin;
CREATE SCHEMA IF NOT EXISTS lg AUTHORIZATION cm_admin;
GRANT ALL ON DATABASE caremem TO cm_admin;
GRANT USAGE ON SCHEMA cm, lg TO cm_app, cm_engine, cm_reader;
-- Table-level grants are applied by migration 0003_security and cm.jobs.migrate.
