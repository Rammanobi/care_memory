-- =============================================================================
-- 0007_roles_grants.sql  (contracts-v1)  PostgreSQL 16
-- Group roles (NOLOGIN) and grants. Login users are created by infra (lane I)
-- and granted one of these roles:
--   cm_app    : cm-api / cm-worker. Reads everything; writes L0, reviews, outbox, ops.
--   cm_engine : cm-nightly / cm-sweeper / cm-eval. Writes L1-L3 projections.
--   cm_reader : dashboard query tools. Views only.
--   cm_admin  : migrations, seed, erasure procedure (owner of the schema objects).
-- Run as the migration owner. Lane B grants SELECT on its own views to cm_reader.
-- =============================================================================

DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cm_app')    THEN CREATE ROLE cm_app    NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cm_engine') THEN CREATE ROLE cm_engine NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cm_reader') THEN CREATE ROLE cm_reader NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cm_admin')  THEN CREATE ROLE cm_admin  NOLOGIN; END IF;
END
$roles$;

REVOKE ALL ON SCHEMA cm FROM PUBLIC;
GRANT USAGE ON SCHEMA cm TO cm_app, cm_engine, cm_reader, cm_admin;
GRANT ALL   ON SCHEMA cm TO cm_admin;
GRANT ALL ON ALL TABLES    IN SCHEMA cm TO cm_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA cm TO cm_admin;

-- ---------------------------------------------------------------- cm_reader
-- Views only; no base tables.
GRANT SELECT ON cm.v_contact_screening, cm.guideline_chunks TO cm_reader;

-- ---------------------------------------------------------------- cm_app
GRANT SELECT ON ALL TABLES IN SCHEMA cm TO cm_app;
GRANT INSERT ON cm.events, cm.consents, cm.audit_log TO cm_app;              -- append-only tables
GRANT INSERT, UPDATE ON
  cm.persons, cm.identity_vault, cm.patients, cm.support_assignments, cm.channel_bindings,
  cm.household_contacts,
  cm.task_runs, cm.approvals, cm.review_decisions, cm.approval_tokens, cm.edit_examples,
  cm.templates, cm.outbox, cm.gmail_state,
  cm.memory_cards, cm.card_citations, cm.hypothesis_requests,
  cm.documents, cm.text_chunks,
  cm.auth_credentials, cm.settings, cm.erasure_requests,
  cm.sim_clock, cm.eval_runs, cm.sim_inbox,
  cm.mock_nikshay_patients, cm.mock_nikshay_payments
TO cm_app;
GRANT DELETE ON cm.sim_inbox, cm.mock_nikshay_payments TO cm_app;           -- demo resets only
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA cm TO cm_app;

-- ---------------------------------------------------------------- cm_engine
GRANT SELECT ON ALL TABLES IN SCHEMA cm TO cm_engine;
GRANT INSERT, UPDATE, DELETE ON
  cm.features_daily, cm.beliefs, cm.belief_evidence, cm.hypothesis_requests,
  cm.conflicts, cm.risk_scores, cm.memory_cards, cm.card_citations, cm.household_contacts
TO cm_engine;
GRANT INSERT ON cm.events, cm.audit_log TO cm_engine;                       -- system events (ContextNote, rules)
GRANT INSERT, UPDATE ON
  cm.task_runs, cm.approvals, cm.outbox, cm.eval_runs, cm.sim_clock, cm.erasure_requests, cm.gmail_state
TO cm_engine;                                                               -- sweeper ladder, R6 gate, eval cache
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA cm TO cm_engine;

-- ---------------------------------------------------------------- LangGraph schema
-- Tables are created by PostgresSaver.setup() / PostgresStore.setup() in cm-migrate,
-- run as the migration owner; default privileges hand them to cm_app / cm_engine.
GRANT USAGE ON SCHEMA lg TO cm_app, cm_engine;
GRANT ALL   ON SCHEMA lg TO cm_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA lg GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cm_app, cm_engine;
ALTER DEFAULT PRIVILEGES IN SCHEMA lg GRANT USAGE, SELECT ON SEQUENCES TO cm_app, cm_engine;

-- Future cm tables created by later migrations: readable by app and engine
-- (write grants must be added explicitly by the migration that creates them).
ALTER DEFAULT PRIVILEGES IN SCHEMA cm GRANT SELECT ON TABLES TO cm_app, cm_engine;
ALTER DEFAULT PRIVILEGES IN SCHEMA cm GRANT USAGE, SELECT ON SEQUENCES TO cm_app, cm_engine;
