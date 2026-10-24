-- =============================================================================
-- 0001_core.sql  (L0, contracts-v1)  PostgreSQL 16
-- Schema cm, extensions, shared trigger functions, org, identity, consent,
-- events (L0, append-only) and the household_contacts projection.
-- Names follow INTEGRATION_DECISIONS.md (task_runs, approval_id, recorded_at).
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector >= 0.7 required for halfvec (asserted by cm-migrate)

CREATE SCHEMA IF NOT EXISTS cm;
CREATE SCHEMA IF NOT EXISTS lg;          -- LangGraph PostgresSaver / PostgresStore tables (created by setup())

-- -----------------------------------------------------------------------------
-- Shared trigger functions
-- -----------------------------------------------------------------------------

-- INSERT-only guard. The ONLY bypass is cm.erase_person() (lane A), which runs
--   SET LOCAL cm.allow_erasure = 'on'
-- inside its transaction before replacing rows with tombstones.
CREATE OR REPLACE FUNCTION cm.forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF current_setting('cm.allow_erasure', true) = 'on' THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'cm.%: % is not allowed (append-only table)', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END;
$$;

-- Keeps updated_at current on mutable rows.
CREATE OR REPLACE FUNCTION cm.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- -----------------------------------------------------------------------------
-- Org
-- -----------------------------------------------------------------------------

CREATE TABLE cm.districts (
  district_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL UNIQUE,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE cm.blocks (
  block_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  district_id  uuid NOT NULL REFERENCES cm.districts(district_id),
  name         text NOT NULL,                       -- neutral "Block A".."Block E"
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (district_id, name)
);
CREATE INDEX blocks_district_idx ON cm.blocks (district_id);

CREATE TABLE cm.clinics (
  clinic_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  block_id     uuid NOT NULL REFERENCES cm.blocks(block_id),
  name         text NOT NULL,
  facility_code text UNIQUE,                        -- Ni-kshay facility code (mock)
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (block_id, name)
);
CREATE INDEX clinics_block_idx ON cm.clinics (block_id);

-- -----------------------------------------------------------------------------
-- Identity
-- -----------------------------------------------------------------------------

CREATE TABLE cm.persons (
  person_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  role         text NOT NULL
               CHECK (role IN ('patient','supporter','doctor','chemist','lab','sts','dto','admin')),
  token        text NOT NULL UNIQUE
               CHECK (token ~ '^[PSDCLTXA]-[0-9]{2,4}$'),   -- P-0042, S-07, D-02, C-03 ...
  clinic_id    uuid REFERENCES cm.clinics(clinic_id),
  district_id  uuid REFERENCES cm.districts(district_id),
  backup_for   uuid REFERENCES cm.persons(person_id),       -- backup doctor (sweeper 36 h step)
  created_at   timestamptz NOT NULL DEFAULT now(),
  CHECK (backup_for IS NULL OR backup_for <> person_id)
);
CREATE INDEX persons_role_clinic_idx ON cm.persons (role, clinic_id);
CREATE INDEX persons_district_idx    ON cm.persons (district_id);
CREATE INDEX persons_backup_for_idx  ON cm.persons (backup_for) WHERE backup_for IS NOT NULL;

-- PII vault: AES-GCM with a per-person DEK wrapped by the Secret Manager master key.
-- Erasure = crypto-shred (dek_wrapped set to NULL / row deleted by cm.erase_person()).
CREATE TABLE cm.identity_vault (
  person_id    uuid PRIMARY KEY REFERENCES cm.persons(person_id) ON DELETE CASCADE,
  enc_name     bytea,
  enc_phone    bytea,
  enc_email    bytea,
  dek_wrapped  bytea,
  lang         text NOT NULL DEFAULT 'en' CHECK (lang IN ('en','te','hi')),
  phone_hmac   bytea,                               -- blind index (exact search, P1)
  nikshay_hmac bytea,
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX identity_vault_phone_hmac_idx   ON cm.identity_vault (phone_hmac)   WHERE phone_hmac IS NOT NULL;
CREATE INDEX identity_vault_nikshay_hmac_idx ON cm.identity_vault (nikshay_hmac) WHERE nikshay_hmac IS NOT NULL;

CREATE TABLE cm.patients (
  patient_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  person_id       uuid NOT NULL UNIQUE REFERENCES cm.persons(person_id),
  clinic_id       uuid NOT NULL REFERENCES cm.clinics(clinic_id),
  treatment_start date NOT NULL,
  regimen         text NOT NULL,                    -- cache; R2 reads the latest RegimenChange event
  phase           text NOT NULL DEFAULT 'intensive'
                  CHECK (phase IN ('intensive','continuation','completed')),
  status          text NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','records_only','paused','completed','erased')),
  channel_profile jsonb NOT NULL DEFAULT '{}'::jsonb,   -- cached api.ChannelProfile
  nikshay_id      text UNIQUE,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX patients_clinic_status_idx ON cm.patients (clinic_id, status);
CREATE TRIGGER patients_touch BEFORE UPDATE ON cm.patients
  FOR EACH ROW EXECUTE FUNCTION cm.touch_updated_at();

CREATE TABLE cm.support_assignments (
  patient_id   uuid NOT NULL REFERENCES cm.patients(patient_id),
  supporter_id uuid NOT NULL REFERENCES cm.persons(person_id),
  from_date    date NOT NULL,
  to_date      date,
  PRIMARY KEY (patient_id, supporter_id, from_date),
  CHECK (to_date IS NULL OR to_date >= from_date)
);
CREATE INDEX support_assignments_supporter_idx ON cm.support_assignments (supporter_id, from_date);

CREATE TABLE cm.channel_bindings (
  person_id         uuid NOT NULL REFERENCES cm.persons(person_id),
  channel           text NOT NULL CHECK (channel IN ('telegram','gmail','web','webpush')),
  external_id       text,                           -- chat_id / email / push endpoint (NULL while pending)
  bound_at          timestamptz,
  invite_code       text UNIQUE,
  invite_expires_at timestamptz,
  status            text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','active','blocked','revoked')),
  meta              jsonb NOT NULL DEFAULT '{}'::jsonb,   -- web-push keys etc.
  PRIMARY KEY (person_id, channel),
  CHECK (status = 'pending' OR external_id IS NOT NULL)
);
CREATE UNIQUE INDEX channel_bindings_external_uq ON cm.channel_bindings (channel, external_id)
  WHERE external_id IS NOT NULL AND status IN ('active','blocked');

-- Consent ledger: append-only, read as latest per (person, source, purpose).
CREATE TABLE cm.consents (
  consent_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  person_id      uuid NOT NULL REFERENCES cm.persons(person_id),
  source         text NOT NULL
                 CHECK (source IN ('telegram','web','supporter','gmail','calendar','wearable','chemist','lab','portal')),
  purpose        text NOT NULL
                 CHECK (purpose IN ('daily_checkin','care_coordination','supporter_sharing','programme_monitoring')),
  state          text NOT NULL CHECK (state IN ('granted','withdrawn')),
  effective_at   timestamptz NOT NULL,
  via            text NOT NULL CHECK (via ~ '^(console|telegram|web|paper|supporter:S-[0-9]+)$'),
  notice_version text NOT NULL DEFAULT 'v1',
  recorded_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX consents_latest_idx ON cm.consents (person_id, source, purpose, effective_at DESC);
CREATE TRIGGER consents_append_only BEFORE UPDATE OR DELETE ON cm.consents
  FOR EACH ROW EXECUTE FUNCTION cm.forbid_mutation();

-- -----------------------------------------------------------------------------
-- L0: events (bitemporal, append-only)
-- -----------------------------------------------------------------------------

CREATE TABLE cm.events (
  event_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id      uuid NOT NULL REFERENCES cm.patients(patient_id),
  type            text NOT NULL CHECK (type IN (
                    'DoseCheckin','SymptomReport','SupporterVisit','PillCount','Dispense','LabResult',
                    'WeightReport','PaymentReport','PortalPayment','PortalRegistration','WearableReading',
                    'ReviewDecisionEvent','ContextNote','IdentityLinked','BeliefRetired','Tombstone',
                    'CheckinPrompt','RegimenChange','ChannelUnreachable','HouseholdContactEvent','ConsentEvent')),
  occurred_at     timestamptz NOT NULL,
  recorded_at     timestamptz NOT NULL,
  source          text NOT NULL CHECK (source IN (
                    'telegram','web','supporter','gmail','calendar','wearable','chemist','lab','portal',
                    'system','console')),
  reporter_id     uuid REFERENCES cm.persons(person_id),
  reporter_mode   text NOT NULL CHECK (reporter_mode IN ('self','witnessed','told','record')),
  channel         text,
  consent_id      uuid REFERENCES cm.consents(consent_id),
  payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
  supersedes      uuid REFERENCES cm.events(event_id),
  idempotency_key text NOT NULL UNIQUE CHECK (length(idempotency_key) BETWEEN 3 AND 255),
  sim_run_id      uuid,
  -- every non-system event carries its authorising consent (P5)
  CHECK (consent_id IS NOT NULL OR source IN ('system','console') OR type IN ('Tombstone','ConsentEvent')),
  CHECK (supersedes IS NULL OR supersedes <> event_id)
);
CREATE INDEX events_patient_occurred_idx ON cm.events (patient_id, occurred_at);
CREATE INDEX events_patient_recorded_idx ON cm.events (patient_id, recorded_at);
CREATE INDEX events_patient_type_idx     ON cm.events (patient_id, type, occurred_at);
CREATE INDEX events_consent_idx          ON cm.events (consent_id) WHERE consent_id IS NOT NULL;
CREATE INDEX events_supersedes_idx       ON cm.events (supersedes) WHERE supersedes IS NOT NULL;
CREATE INDEX events_sim_run_idx          ON cm.events (sim_run_id) WHERE sim_run_id IS NOT NULL;
CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE ON cm.events
  FOR EACH ROW EXECUTE FUNCTION cm.forbid_mutation();

-- -----------------------------------------------------------------------------
-- household_contacts: projection of HouseholdContactEvent (rebuildable, P0)
-- -----------------------------------------------------------------------------

CREATE TABLE cm.household_contacts (
  contact_id      uuid PRIMARY KEY,
  patient_id      uuid NOT NULL REFERENCES cm.patients(patient_id),
  relation        text CHECK (relation IN ('spouse','child','parent','sibling','other')),
  age_band        text CHECK (age_band IN ('<5','5-14','15-59','60+')),
  enc_name        bytea,                            -- encrypted under the PATIENT's DEK
  symptoms        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {cough_2w, fever, weight_loss, night_sweats}
  flagged         boolean NOT NULL DEFAULT false,   -- age_band='<5' OR any(symptoms) (set by repo)
  screened_at     timestamptz,
  referred        boolean NOT NULL DEFAULT false,
  doctor_decision text CHECK (doctor_decision IN ('refer_test','tpt_decided','no_action')),
  decided_by      uuid REFERENCES cm.persons(person_id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (doctor_decision IS NULL OR decided_by IS NOT NULL)
);
CREATE INDEX household_contacts_patient_idx ON cm.household_contacts (patient_id);
CREATE INDEX household_contacts_unscreened_idx ON cm.household_contacts (patient_id) WHERE screened_at IS NULL;
CREATE TRIGGER household_contacts_touch BEFORE UPDATE ON cm.household_contacts
  FOR EACH ROW EXECUTE FUNCTION cm.touch_updated_at();
