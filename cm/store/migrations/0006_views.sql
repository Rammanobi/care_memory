-- =============================================================================
-- 0006_views.sql  (contracts-v1)  PostgreSQL 16
-- Contract views owned by L0. Lane B adds v_patient_summary, v_district_daily
-- (materialised), v_review_sla, v_supporter_activity, v_payments_stuck and the
-- cm.notify_live() triggers in a later migration (0008_views_b.sql or higher),
-- granting SELECT on each new view to cm_reader.
-- guideline_chunks lives in 0004_rag.sql.
-- =============================================================================

-- v_contact_screening (T1): household contact screening KPI per block, at the
-- current sim day (sim_clock active row; falls back to current_date).
-- patients_overdue = patients at or past contacts_due_day (settings.thresholds,
-- default 14) with zero listed contacts or any unscreened contact, excluding
-- patients with a ContextNote{kind:'household_declined'} (same logic as R6).
CREATE VIEW cm.v_contact_screening AS
WITH clk AS (
  SELECT coalesce(
           (SELECT s.day0_date + s.sim_day FROM cm.sim_clock s WHERE s.active LIMIT 1),
           current_date) AS as_of
),
due AS (
  SELECT coalesce(
           (SELECT (st.value ->> 'contacts_due_day')::int FROM cm.settings st WHERE st.key = 'thresholds'),
           14) AS due_day
),
pt AS (
  SELECT p.patient_id, b.district_id, c.block_id, p.treatment_start
    FROM cm.patients p
    JOIN cm.clinics c ON c.clinic_id = p.clinic_id
    JOIN cm.blocks  b ON b.block_id  = c.block_id
   WHERE p.status IN ('active', 'records_only')
),
hc AS (
  SELECT h.patient_id,
         count(*)                                       AS listed,
         count(*) FILTER (WHERE h.screened_at IS NOT NULL) AS screened,
         count(*) FILTER (WHERE h.referred)             AS referred,
         count(*) FILTER (WHERE h.screened_at IS NULL)  AS unscreened
    FROM cm.household_contacts h
   GROUP BY h.patient_id
),
declined AS (
  SELECT DISTINCT e.patient_id
    FROM cm.events e
   WHERE e.type = 'ContextNote'
     AND e.payload ->> 'kind' = 'household_declined'
)
SELECT pt.district_id,
       pt.block_id,
       clk.as_of,
       coalesce(sum(hc.listed), 0)::int   AS contacts_listed,
       coalesce(sum(hc.screened), 0)::int AS contacts_screened,
       coalesce(sum(hc.referred), 0)::int AS contacts_referred,
       count(*) FILTER (
         WHERE (clk.as_of - pt.treatment_start) >= due.due_day
           AND d.patient_id IS NULL
           AND (coalesce(hc.listed, 0) = 0 OR hc.unscreened > 0)
       )::int                             AS patients_overdue
  FROM pt
  CROSS JOIN clk
  CROSS JOIN due
  LEFT JOIN hc       ON hc.patient_id = pt.patient_id
  LEFT JOIN declined d ON d.patient_id = pt.patient_id
 WHERE pt.treatment_start <= clk.as_of
 GROUP BY pt.district_id, pt.block_id, clk.as_of;
