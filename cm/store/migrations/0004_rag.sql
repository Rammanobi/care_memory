-- =============================================================================
-- 0004_rag.sql  (contracts-v1)  PostgreSQL 16 + pgvector
-- RAG-lite (T6): documents + text_chunks (halfvec(1536), HNSW, generated tsvector)
-- and the guideline_chunks compatibility view. P0 holds guidelines only.
--
-- Vector type: halfvec(1536) when pgvector >= 0.7 (cm-migrate asserts this on
-- Cloud SQL). Fallback flag: cm-migrate runs
--   SET cm.rag_vector_type = 'vector';
-- before this file when RAG_VECTOR_TYPE=vector, which switches to vector(1536).
-- Citation refs: [G:chunk_id] guideline, [D:chunk_id] patient document.
-- =============================================================================

CREATE TABLE cm.documents (
  document_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_token    text CHECK (patient_token IS NULL OR patient_token ~ '^P-[0-9]{4}$'),   -- NULL for guidelines
  doc_type         text NOT NULL CHECK (doc_type IN
                     ('lab','prescription','sales_csv','email','supporter_note','guideline','checkin')),
  source           text NOT NULL,                    -- telegram, gmail, upload, chemist_feed, seed
  author_role      text NOT NULL CHECK (author_role IN ('patient','supporter','doctor','lab','chemist','system')),
  occurred_at      timestamptz,
  recorded_at      timestamptz NOT NULL DEFAULT now(),
  consent_id       uuid REFERENCES cm.consents(consent_id),
  language         text NOT NULL DEFAULT 'en',
  confidence       real CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  extraction_model text,
  content_hash     bytea NOT NULL UNIQUE,            -- sha256 of normalised text
  version          integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  supersedes       uuid REFERENCES cm.documents(document_id),
  sensitivity      text NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal','hiv_adjacent','mental_health')),
  retention_until  date,
  gcs_uri          text CHECK (gcs_uri IS NULL OR gcs_uri LIKE 'gs://%'),
  status           text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','withdrawn')),
  extra            jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK ((doc_type = 'guideline') = (patient_token IS NULL)),
  CHECK (doc_type = 'guideline' OR consent_id IS NOT NULL OR author_role = 'system')
);
CREATE INDEX documents_patient_idx ON cm.documents (patient_token, doc_type, occurred_at DESC) WHERE status = 'active';
CREATE INDEX documents_consent_idx ON cm.documents (consent_id) WHERE consent_id IS NOT NULL;

DO $rag$
DECLARE
  vtype  text := coalesce(nullif(current_setting('cm.rag_vector_type', true), ''), 'halfvec');
  ops    text;
BEGIN
  IF vtype NOT IN ('halfvec', 'vector') THEN
    RAISE EXCEPTION 'cm.rag_vector_type must be halfvec or vector, got %', vtype;
  END IF;
  ops := vtype || '_cosine_ops';

  EXECUTE format($ddl$
    CREATE TABLE cm.text_chunks (
      chunk_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      document_id     uuid NOT NULL REFERENCES cm.documents(document_id) ON DELETE CASCADE,
      parent_id       uuid REFERENCES cm.text_chunks(chunk_id) ON DELETE CASCADE,
      patient_token   text CHECK (patient_token IS NULL OR patient_token ~ '^P-[0-9]{4}$'),
      doc_type        text NOT NULL CHECK (doc_type IN
                        ('lab','prescription','sales_csv','email','supporter_note','guideline','checkin')),
      status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','withdrawn')),
      occurred_at     timestamptz,
      recorded_at     timestamptz NOT NULL DEFAULT now(),
      consent_id      uuid REFERENCES cm.consents(consent_id),
      language        text NOT NULL DEFAULT 'en',
      sensitivity     text NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal','hiv_adjacent','mental_health')),
      content         text NOT NULL,
      content_hash    bytea NOT NULL,
      embedding       %1$s(1536),
      embedding_model text,
      tsv             tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content)) STORED,
      extra           jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {doc, section, page, loc}
      UNIQUE (document_id, content_hash),
      CHECK (embedding IS NULL OR embedding_model IS NOT NULL)
    )$ddl$, vtype);

  EXECUTE format(
    'CREATE INDEX text_chunks_hnsw ON cm.text_chunks USING hnsw (embedding %s) WITH (m = 16, ef_construction = 64)', ops);
  EXECUTE format(
    'CREATE INDEX text_chunks_guideline_hnsw ON cm.text_chunks USING hnsw (embedding %s) '
    'WITH (m = 16, ef_construction = 64) WHERE doc_type = ''guideline'' AND status = ''active''', ops);
END
$rag$;

CREATE INDEX text_chunks_filter_idx   ON cm.text_chunks (patient_token, doc_type, occurred_at DESC) WHERE status = 'active';
CREATE INDEX text_chunks_tsv_idx      ON cm.text_chunks USING gin (tsv);
CREATE INDEX text_chunks_document_idx ON cm.text_chunks (document_id);
CREATE INDEX text_chunks_consent_idx  ON cm.text_chunks (consent_id) WHERE consent_id IS NOT NULL;

-- Compatibility view (arch §5 guideline_chunks): active guideline chunks only.
CREATE VIEW cm.guideline_chunks AS
  SELECT c.chunk_id,
         c.extra ->> 'doc'     AS doc,
         c.extra ->> 'section' AS section,
         c.content             AS text,
         c.embedding,
         c.tsv,
         c.language,
         c.document_id
    FROM cm.text_chunks c
   WHERE c.doc_type = 'guideline'
     AND c.status = 'active';
