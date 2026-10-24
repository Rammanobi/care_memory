-- =============================================================================
-- 0003_memory.sql  (contracts-v1)  PostgreSQL 16
-- L1-L3 projections written by cm-nightly (role cm_engine): features, beliefs,
-- hypotheses, conflicts (R1-R6), risk (two heads), memory cards + citations.
-- All keyed by as_of so "what did we know on day N" is a plain read.
-- =============================================================================

CREATE TABLE cm.features_daily (
  patient_id     uuid NOT NULL REFERENCES cm.patients(patient_id),
  as_of          date NOT NULL,
  features       jsonb NOT NULL,                     -- memory.FeatureVector
  computed_at    timestamptz NOT NULL DEFAULT now(),
  engine_version text NOT NULL,
  PRIMARY KEY (patient_id, as_of)
);

-- One row per (belief, as_of) snapshot.
CREATE TABLE cm.beliefs (
  belief_id      uuid NOT NULL,
  as_of          date NOT NULL,
  patient_id     uuid NOT NULL REFERENCES cm.patients(patient_id),
  kind           text NOT NULL CHECK (kind IN
                   ('weekday_miss','payday_miss','reporter_trust','reply_drift','refill_gap','weight_trend')),
  subject        text,                               -- 'thu', a reporter token ...
  state          text NOT NULL CHECK (state IN ('hypothesis','confirmed','dormant','retired')),
  posterior      real NOT NULL CHECK (posterior >= 0 AND posterior <= 1),
  ci_low         real,
  ci_high        real,
  n_instances    integer NOT NULL DEFAULT 0 CHECK (n_instances >= 0),
  first_seen     date NOT NULL,
  confirmed_at   date,
  retired_at     date,
  retired_reason text,
  PRIMARY KEY (belief_id, as_of),
  CHECK (ci_low IS NULL OR ci_high IS NULL OR ci_low <= ci_high),
  CHECK (state <> 'retired' OR retired_at IS NOT NULL)
);
CREATE INDEX beliefs_patient_asof_idx ON cm.beliefs (patient_id, as_of);
CREATE INDEX beliefs_patient_kind_idx ON cm.beliefs (patient_id, kind, subject);

CREATE TABLE cm.belief_evidence (
  belief_id uuid NOT NULL,
  event_id  uuid NOT NULL REFERENCES cm.events(event_id),
  role      text NOT NULL CHECK (role IN ('support','contradict')),
  PRIMARY KEY (belief_id, event_id)
);
CREATE INDEX belief_evidence_event_idx ON cm.belief_evidence (event_id);

CREATE TABLE cm.hypothesis_requests (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id       uuid NOT NULL REFERENCES cm.patients(patient_id),
  proposed_by      text NOT NULL,                    -- agent name / thread_id
  kind             text NOT NULL CHECK (kind IN
                     ('weekday_miss','payday_miss','reporter_trust','reply_drift','refill_gap','weight_trend')),
  params           jsonb NOT NULL DEFAULT '{}'::jsonb,
  status           text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','testing','confirmed','rejected','inconclusive')),
  result_belief_id uuid,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX hypothesis_requests_pending_idx ON cm.hypothesis_requests (patient_id) WHERE status = 'pending';

CREATE TABLE cm.conflicts (
  conflict_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id   uuid NOT NULL REFERENCES cm.patients(patient_id),
  rule         text NOT NULL CHECK (rule IN ('R1','R2','R3','R4','R5','R6')),
  tier         text NOT NULL CHECK (tier IN ('red','amber','green')),
  title        text NOT NULL,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,   -- citation refs ["E:uuid", ...]
  opened_as_of date NOT NULL,
  closed_as_of date,
  CHECK (jsonb_typeof(evidence_ids) = 'array'),
  CHECK (closed_as_of IS NULL OR closed_as_of >= opened_as_of)
);
CREATE INDEX conflicts_patient_open_idx ON cm.conflicts (patient_id, opened_as_of, closed_as_of);
CREATE INDEX conflicts_open_rule_idx    ON cm.conflicts (rule, tier) WHERE closed_as_of IS NULL;
-- at most one open conflict per (patient, rule)
CREATE UNIQUE INDEX conflicts_one_open_uq ON cm.conflicts (patient_id, rule) WHERE closed_as_of IS NULL;

-- p = dropout14 head (displayed); p_miss7 = second head (M4).
CREATE TABLE cm.risk_scores (
  patient_id    uuid NOT NULL REFERENCES cm.patients(patient_id),
  as_of         date NOT NULL,
  p             real NOT NULL CHECK (p >= 0 AND p <= 1),
  ci_low        real NOT NULL CHECK (ci_low >= 0 AND ci_low <= 1),
  ci_high       real NOT NULL CHECK (ci_high >= 0 AND ci_high <= 1),
  p_miss7       real CHECK (p_miss7 >= 0 AND p_miss7 <= 1),
  miss7_ci_low  real CHECK (miss7_ci_low >= 0 AND miss7_ci_low <= 1),
  miss7_ci_high real CHECK (miss7_ci_high >= 0 AND miss7_ci_high <= 1),
  drivers       jsonb NOT NULL DEFAULT '[]'::jsonb,  -- memory.Driver[]
  model_version text NOT NULL,
  computed_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (patient_id, as_of),
  CHECK (ci_low <= ci_high),
  CHECK (miss7_ci_low IS NULL OR miss7_ci_high IS NULL OR miss7_ci_low <= miss7_ci_high)
);
CREATE INDEX risk_scores_asof_p_idx ON cm.risk_scores (as_of, p DESC);

CREATE TABLE cm.memory_cards (
  card_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id    uuid NOT NULL REFERENCES cm.patients(patient_id),
  as_of         date NOT NULL,
  audience      text NOT NULL CHECK (audience IN ('doctor','supporter')),
  body          text NOT NULL,
  sentences     jsonb NOT NULL DEFAULT '[]'::jsonb,  -- memory.Sentence[]
  cut_ratio     real NOT NULL DEFAULT 0 CHECK (cut_ratio >= 0 AND cut_ratio <= 1),
  fallback_used boolean NOT NULL DEFAULT false,
  status        text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','rejected')),
  approval_id   uuid REFERENCES cm.approvals(approval_id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (status = 'draft' OR approval_id IS NOT NULL)
);
CREATE INDEX memory_cards_patient_idx ON cm.memory_cards (patient_id, audience, as_of DESC);
CREATE INDEX memory_cards_approval_idx ON cm.memory_cards (approval_id) WHERE approval_id IS NOT NULL;

CREATE TABLE cm.card_citations (
  card_id      uuid NOT NULL REFERENCES cm.memory_cards(card_id) ON DELETE CASCADE,
  sentence_idx integer NOT NULL CHECK (sentence_idx >= 0),
  ref_type     text NOT NULL CHECK (ref_type IN ('E','B','C','R','G','D')),
  ref_id       text NOT NULL,                        -- uuid, or 'P-0042@60' for R
  PRIMARY KEY (card_id, sentence_idx, ref_type, ref_id)
);
CREATE INDEX card_citations_ref_idx ON cm.card_citations (ref_type, ref_id);
