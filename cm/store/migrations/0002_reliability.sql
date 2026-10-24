-- =============================================================================
-- 0002_reliability.sql  (contracts-v1)  PostgreSQL 16
-- task_runs, the doctor-gate queue (approvals + decisions + tokens + edits),
-- templates, the transactional outbox with the DB-level doctor gate,
-- audit_log (append-only) and gmail_state.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- task_runs (NOT "jobs"). task_id = Cloud Task name (colon-free).
-- -----------------------------------------------------------------------------

CREATE TABLE cm.task_runs (
  task_id         text PRIMARY KEY CHECK (task_id ~ '^[A-Za-z0-9_-]+$' AND length(task_id) <= 500),
  task_type       text NOT NULL CHECK (task_type IN (
                    'ingest_event','nightly_patient','investigate','prepare_visit_list','doctor_digest','consent_change',
                    'resume','send','drain_outbox','checkins','checkin_nudge','digest','visit_lists','gmail_fetch',
                    'gmail_watch_renew','gmail_sweep','portal_sync','calendar_sync','district_report','nightly','seed',
                    'eval','sweep','migrate')),
  thread_id       text CHECK (length(thread_id) < 255),
  patient_id      uuid REFERENCES cm.patients(patient_id),
  state           text NOT NULL DEFAULT 'queued'
                  CHECK (state IN ('queued','running','waiting_human','retrying','succeeded','failed')),
  attempt         integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  heartbeat_at    timestamptz,
  worker_instance text,
  error           text,
  error_class     text CHECK (error_class IN ('retryable','spend_cap','auth','invalid','unknown')),
  progress        real CHECK (progress IS NULL OR (progress >= 0 AND progress <= 1)),
  step            text,
  tokens_in       integer NOT NULL DEFAULT 0 CHECK (tokens_in >= 0),
  tokens_out      integer NOT NULL DEFAULT 0 CHECK (tokens_out >= 0),
  cost_usd        numeric(12,6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX task_runs_state_heartbeat_idx ON cm.task_runs (state, heartbeat_at) WHERE state IN ('running','retrying');
CREATE INDEX task_runs_waiting_idx         ON cm.task_runs (updated_at) WHERE state = 'waiting_human';
CREATE INDEX task_runs_thread_idx          ON cm.task_runs (thread_id) WHERE thread_id IS NOT NULL;
CREATE INDEX task_runs_type_created_idx    ON cm.task_runs (task_type, created_at DESC);
CREATE INDEX task_runs_patient_idx         ON cm.task_runs (patient_id) WHERE patient_id IS NOT NULL;
CREATE TRIGGER task_runs_touch BEFORE UPDATE ON cm.task_runs
  FOR EACH ROW EXECUTE FUNCTION cm.touch_updated_at();

-- -----------------------------------------------------------------------------
-- templates (doctor-approved once; Green tier)
-- -----------------------------------------------------------------------------

CREATE TABLE cm.templates (
  template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key         text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{2,63}$'),
  lang        text NOT NULL CHECK (lang IN ('en','te','hi')),
  body        text NOT NULL CHECK (length(body) <= 2000),
  slots       text[] NOT NULL DEFAULT '{}',
  tier        text NOT NULL DEFAULT 'green' CHECK (tier IN ('red','amber','green')),
  status      text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','retired')),
  approved_by uuid REFERENCES cm.persons(person_id),
  approved_at timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE UNIQUE INDEX templates_one_approved_uq ON cm.templates (key, lang) WHERE status = 'approved';
CREATE INDEX templates_status_idx ON cm.templates (status, key);

-- -----------------------------------------------------------------------------
-- approvals = the doctor queue (API model review.ReviewItem)
-- -----------------------------------------------------------------------------

CREATE TABLE cm.approvals (
  approval_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id        uuid REFERENCES cm.patients(patient_id),
  thread_id         text NOT NULL CHECK (length(thread_id) < 255),
  interrupt_id      text NOT NULL,
  task_id           text REFERENCES cm.task_runs(task_id) ON DELETE SET NULL,
  proposal_group_id uuid,                            -- links re-drafts
  graph_kind        text NOT NULL CHECK (graph_kind IN ('deep','lg')),
  tier              text NOT NULL CHECK (tier IN ('red','amber','green')),
  kind              text NOT NULL CHECK (kind IN (
                      'card','brief','visit_list','conflict','identity','digest','needs_human',
                      'lab_confirm','contact_review','district_report')),
  payload           jsonb NOT NULL,                  -- review.ProposalOut (incl. recipients)
  evidence          jsonb NOT NULL DEFAULT '[]'::jsonb,   -- review.EvidenceItem[]
  status            text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','edited','rejected','expired','manual')),
  redraft_count     integer NOT NULL DEFAULT 0 CHECK (redraft_count BETWEEN 0 AND 2),
  sample_reason     text CHECK (sample_reason IN ('anomaly','random_10pct')),
  created_at        timestamptz NOT NULL DEFAULT now(),
  due_at            timestamptz NOT NULL,            -- stored: Red +4h, Amber next 12:00 IST, Green end of day
  expires_at        timestamptz NOT NULL,
  reminded_at       timestamptz,
  escalated_at      timestamptz,
  CONSTRAINT approvals_thread_interrupt_uq UNIQUE (thread_id, interrupt_id),
  CHECK (sample_reason IS NULL OR tier = 'green'),
  CHECK (graph_kind = 'deep' OR interrupt_id LIKE 'gate:%'),
  CHECK (jsonb_typeof(evidence) = 'array'),
  CHECK (expires_at >= created_at)
);
CREATE INDEX approvals_queue_idx      ON cm.approvals (status, tier, due_at);
CREATE INDEX approvals_pending_exp_idx ON cm.approvals (expires_at) WHERE status = 'pending';
CREATE INDEX approvals_patient_idx    ON cm.approvals (patient_id, created_at DESC);
CREATE INDEX approvals_group_idx      ON cm.approvals (proposal_group_id) WHERE proposal_group_id IS NOT NULL;
CREATE INDEX approvals_task_idx       ON cm.approvals (task_id) WHERE task_id IS NOT NULL;

CREATE TABLE cm.review_decisions (
  decision_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_id     uuid NOT NULL UNIQUE REFERENCES cm.approvals(approval_id),   -- one decision per approval
  doctor_id       uuid REFERENCES cm.persons(person_id),
  action          text NOT NULL CHECK (action IN ('approve','edit','reject','expired')),
  edited          jsonb,
  reason          text CHECK (length(reason) <= 500),
  via             text NOT NULL CHECK (via IN ('console','gmail','sweeper')),
  evidence_viewed boolean NOT NULL DEFAULT false,    -- audit only
  decided_at      timestamptz NOT NULL DEFAULT now(),
  CHECK ((action = 'expired') = (via = 'sweeper')),
  CHECK (doctor_id IS NOT NULL OR via = 'sweeper'),
  CHECK (action <> 'edit' OR edited IS NOT NULL)
);
CREATE INDEX review_decisions_doctor_idx ON cm.review_decisions (doctor_id, decided_at DESC);

-- Single-use Gmail reply tokens (128-bit random, stored hashed, 48 h TTL).
CREATE TABLE cm.approval_tokens (
  token_hash  bytea PRIMARY KEY,
  approval_id uuid NOT NULL REFERENCES cm.approvals(approval_id),
  doctor_id   uuid NOT NULL REFERENCES cm.persons(person_id),
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX approval_tokens_approval_idx ON cm.approval_tokens (approval_id);

CREATE TABLE cm.edit_examples (
  example_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  decision_id uuid NOT NULL UNIQUE REFERENCES cm.review_decisions(decision_id),
  doctor_id   uuid NOT NULL REFERENCES cm.persons(person_id),
  kind        text NOT NULL,
  before      text NOT NULL,
  after       text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  retired_at  timestamptz
);
CREATE INDEX edit_examples_doctor_idx ON cm.edit_examples (doctor_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- outbox (transactional). Only cm/router/outbox_drainer.py sends.
-- DB-LEVEL DOCTOR GATE: a row cannot exist without an approval_id (+ its decision)
-- unless its kind is an allow-listed system kind backed by an APPROVED template.
-- Allow-list must equal review.SYSTEM_OUTBOX_KINDS.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION cm.outbox_system_kinds() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT ARRAY['checkin','checkin_nudge','supporter_proxy','template_prompt','ack','danger_ack',
               'red_alert','escalation_notice','doctor_digest','gmail_echo','consent_echo']::text[]
$$;

CREATE TABLE cm.outbox (
  outbox_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind                text NOT NULL CHECK (kind IN (
                        'card','brief','visit_list','ai_message','calendar_event','district_report','lab_confirm_notice',
                        'checkin','checkin_nudge','supporter_proxy','template_prompt','ack','danger_ack',
                        'red_alert','escalation_notice','doctor_digest','gmail_echo','consent_echo')),
  recipient_id        uuid NOT NULL REFERENCES cm.persons(person_id),
  channel             text NOT NULL CHECK (channel IN ('telegram','gmail','webpush','web_inbox','calendar')),
  body                text,                          -- purged after 30 days; body_sha256 kept
  body_sha256         bytea,
  approval_id         uuid REFERENCES cm.approvals(approval_id),
  decision_id         uuid REFERENCES cm.review_decisions(decision_id),
  template_id         uuid REFERENCES cm.templates(template_id),
  status              text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sending','sent','failed')),
  attempts            integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  next_attempt_at     timestamptz NOT NULL DEFAULT now(),
  locked_by           text,
  locked_at           timestamptz,
  provider_message_id text,
  sent_at             timestamptz,
  last_error          text,
  for_date            date,
  meta                jsonb NOT NULL DEFAULT '{}'::jsonb,   -- buttons, ForceReply, CalendarEventSpec ...
  dedup_key           text NOT NULL UNIQUE,          -- {decision_id|template_key}:{recipient_id}:{channel}:{for_date}[:{n}]
  created_at          timestamptz NOT NULL DEFAULT now(),
  -- arch rule: every row is authorised by a decision or an approved template
  CONSTRAINT outbox_authorised CHECK (decision_id IS NOT NULL OR template_id IS NOT NULL),
  -- doctor gate
  CONSTRAINT outbox_doctor_gate CHECK (
    (approval_id IS NOT NULL AND decision_id IS NOT NULL)
    OR (kind = ANY (cm.outbox_system_kinds()) AND template_id IS NOT NULL)
  ),
  CHECK (status <> 'sent' OR sent_at IS NOT NULL),
  CHECK (status <> 'sending' OR locked_at IS NOT NULL)
);
CREATE INDEX outbox_claim_idx     ON cm.outbox (channel, next_attempt_at) WHERE status = 'pending';
CREATE INDEX outbox_sending_idx   ON cm.outbox (locked_at) WHERE status = 'sending';
CREATE INDEX outbox_recipient_idx ON cm.outbox (recipient_id, created_at DESC);
CREATE INDEX outbox_approval_idx  ON cm.outbox (approval_id) WHERE approval_id IS NOT NULL;

-- Gate consistency the CHECK cannot express: the decision belongs to the approval
-- and is approve/edit; the template (when used) is approved.
CREATE OR REPLACE FUNCTION cm.outbox_gate() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  d_approval uuid;
  d_action   text;
  t_status   text;
BEGIN
  IF NEW.decision_id IS NOT NULL THEN
    SELECT approval_id, action INTO d_approval, d_action
      FROM cm.review_decisions WHERE decision_id = NEW.decision_id;
    IF d_action NOT IN ('approve','edit') THEN
      RAISE EXCEPTION 'outbox: decision % is %, not approve/edit', NEW.decision_id, d_action
        USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.approval_id IS NOT NULL AND d_approval <> NEW.approval_id THEN
      RAISE EXCEPTION 'outbox: decision % does not belong to approval %', NEW.decision_id, NEW.approval_id
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.template_id IS NOT NULL AND NEW.decision_id IS NULL THEN
    SELECT status INTO t_status FROM cm.templates WHERE template_id = NEW.template_id;
    IF t_status IS DISTINCT FROM 'approved' THEN
      RAISE EXCEPTION 'outbox: template % is not approved (%)', NEW.template_id, t_status
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER outbox_gate_trg
  BEFORE INSERT OR UPDATE OF approval_id, decision_id, template_id, kind ON cm.outbox
  FOR EACH ROW EXECUTE FUNCTION cm.outbox_gate();

-- -----------------------------------------------------------------------------
-- audit_log (append-only)
-- -----------------------------------------------------------------------------

CREATE TABLE cm.audit_log (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  at          timestamptz NOT NULL DEFAULT now(),
  actor       text NOT NULL,                         -- person token or 'system'
  role        text NOT NULL,
  action      text NOT NULL,                         -- tool_call, decision, consent, login, detokenise, erasure ...
  tool        text,
  args_hash   text,
  result_ids  text[] NOT NULL DEFAULT '{}',          -- backs the investigator citation check
  patient_id  uuid,                                  -- no FK: audit outlives erasure
  thread_id   text,
  ip          inet
);
CREATE INDEX audit_log_at_idx      ON cm.audit_log (at DESC);
CREATE INDEX audit_log_patient_idx ON cm.audit_log (patient_id, at DESC) WHERE patient_id IS NOT NULL;
CREATE INDEX audit_log_thread_idx  ON cm.audit_log (thread_id) WHERE thread_id IS NOT NULL;
CREATE INDEX audit_log_actor_idx   ON cm.audit_log (actor, at DESC);
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON cm.audit_log
  FOR EACH ROW EXECUTE FUNCTION cm.forbid_mutation();

-- -----------------------------------------------------------------------------
-- gmail_state
-- -----------------------------------------------------------------------------

CREATE TABLE cm.gmail_state (
  mailbox          text PRIMARY KEY,
  history_id       bigint,
  watch_expiration timestamptz,
  last_sweep_at    timestamptz,
  last_push_at     timestamptz
);
