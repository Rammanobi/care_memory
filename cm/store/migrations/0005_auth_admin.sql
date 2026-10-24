-- =============================================================================
-- 0005_auth_admin.sql  (contracts-v1)  PostgreSQL 16
-- auth_credentials, settings, erasure_requests (two distinct approvers),
-- sim_clock, eval_runs, sim_inbox, mock Ni-kshay tables.
-- =============================================================================

-- Passwords: hashlib.scrypt. JWT claim tv must equal token_version.
CREATE TABLE cm.auth_credentials (
  person_id     uuid PRIMARY KEY REFERENCES cm.persons(person_id),
  username      text NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9._-]{3,32}$'),
  password_hash text NOT NULL,
  token_version integer NOT NULL DEFAULT 1 CHECK (token_version >= 1),
  active        boolean NOT NULL DEFAULT true,
  last_login_at timestamptz
);

-- Keys: 'thresholds' (admin.RuleThresholds) and 'channels.{telegram|gmail|calendar|wearable}.enabled'.
-- supporter_web is always on and has no key. Optimistic lock on version.
CREATE TABLE cm.settings (
  key        text PRIMARY KEY CHECK (
               key = 'thresholds'
               OR key ~ '^channels\.(telegram|gmail|calendar|wearable)\.enabled$'),
  value      jsonb NOT NULL,
  version    integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  updated_by uuid REFERENCES cm.persons(person_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (key = 'thresholds' OR jsonb_typeof(value) = 'boolean'),
  CHECK (key <> 'thresholds' OR jsonb_typeof(value) = 'object')
);

-- DPDP erasure: requested by one person, approved by a DIFFERENT person.
-- Executed by cm.erase_person() (lane A) in cm-nightly step C.
CREATE TABLE cm.erasure_requests (
  request_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  person_id    uuid NOT NULL REFERENCES cm.persons(person_id),
  reason       text NOT NULL CHECK (length(reason) BETWEEN 5 AND 500),
  status       text NOT NULL DEFAULT 'awaiting_second_approval'
               CHECK (status IN ('awaiting_second_approval','approved','executing','done','rejected')),
  requested_by uuid NOT NULL REFERENCES cm.persons(person_id),
  requested_at timestamptz NOT NULL DEFAULT now(),
  approved_by  uuid REFERENCES cm.persons(person_id),
  approved_at  timestamptz,
  executed_at  timestamptz,
  error        text,
  CONSTRAINT erasure_two_distinct_approvers CHECK (approved_by IS NULL OR approved_by <> requested_by),
  CONSTRAINT erasure_approved_needs_approver CHECK (
    status NOT IN ('approved','executing','done') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  CONSTRAINT erasure_done_needs_executed_at CHECK (status <> 'done' OR executed_at IS NOT NULL),
  CHECK (person_id <> requested_by)
);
CREATE INDEX erasure_requests_status_idx ON cm.erasure_requests (status, requested_at);
-- at most one open request per person
CREATE UNIQUE INDEX erasure_requests_one_open_uq ON cm.erasure_requests (person_id)
  WHERE status IN ('awaiting_second_approval','approved','executing');

-- One active row (status-agnostic singleton enforced by the partial unique index).
CREATE TABLE cm.sim_clock (
  run_id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seed                    integer NOT NULL,
  sim_day                 integer NOT NULL DEFAULT 0 CHECK (sim_day >= 0),
  day0_date               date NOT NULL,
  max_computed_day        integer NOT NULL DEFAULT 0 CHECK (max_computed_day >= 0),
  escalation_offset_hours real NOT NULL DEFAULT 0 CHECK (escalation_offset_hours >= 0),  -- DEMO_MODE=1 only
  status                  text NOT NULL DEFAULT 'seeding' CHECK (status IN ('seeding','ready')),
  active                  boolean NOT NULL DEFAULT true,
  created_at              timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX sim_clock_one_active_uq ON cm.sim_clock ((true)) WHERE active;

CREATE TABLE cm.eval_runs (
  run_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seed           integer NOT NULL CHECK (seed = 42 OR seed >= 2000),
  gen_version    text NOT NULL,
  engine_version text NOT NULL,
  model_version  text NOT NULL,
  status         text NOT NULL DEFAULT 'running' CHECK (status IN ('running','done','failed')),
  task_id        text REFERENCES cm.task_runs(task_id) ON DELETE SET NULL,
  started_at     timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz,
  report         jsonb,                              -- evalsim.EvalReport
  CONSTRAINT eval_runs_cache_key_uq UNIQUE (seed, gen_version, engine_version, model_version),
  CHECK (status <> 'done' OR (report IS NOT NULL AND finished_at IS NOT NULL))
);

-- Offline phone panels only (CM_OFFLINE=1).
CREATE TABLE cm.sim_inbox (
  id         bigserial PRIMARY KEY,
  persona    text NOT NULL,
  channel    text NOT NULL,
  direction  text NOT NULL CHECK (direction IN ('in','out')),
  body       text NOT NULL,
  buttons    jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sim_inbox_persona_idx ON cm.sim_inbox (persona, id);

-- Mock Ni-kshay portal (filled by cm-seed; mock only).
CREATE TABLE cm.mock_nikshay_patients (
  nikshay_id      text PRIMARY KEY,
  patient_id      uuid REFERENCES cm.patients(patient_id),
  facility_code   text NOT NULL,
  notified_on     date NOT NULL,
  treatment_start date NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE cm.mock_nikshay_payments (
  nikshay_id text NOT NULL REFERENCES cm.mock_nikshay_patients(nikshay_id),
  month      text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  amount     integer NOT NULL CHECK (amount >= 0),
  status     text NOT NULL CHECK (status IN ('paid','pending','failed','unpaid')),
  paid_on    date,
  pfms_ref   text,
  PRIMARY KEY (nikshay_id, month),
  CHECK (status <> 'paid' OR paid_on IS NOT NULL)
);
