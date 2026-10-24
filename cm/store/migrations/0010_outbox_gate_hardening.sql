-- 0010_outbox_gate_hardening.sql (lane A, OpenSpec fix-invariant-bugs; 0009 is reserved for rag_v2).
-- Two holes in the DB-level doctor gate found by tests/invariants/test_db_invariants.py:
--  1. A system-kind row with a DRAFT template passed when it also carried any approve decision
--     (the template check only ran when decision_id was NULL). The template must be approved
--     whenever the row is authorised by the template branch (no approval_id + decision_id pair).
--  2. The body of a pending row could be rewritten after the doctor approved it. The body is now
--     frozen: the only allowed change is the 30-day purge (body -> NULL).

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
  IF NEW.template_id IS NOT NULL AND (NEW.approval_id IS NULL OR NEW.decision_id IS NULL) THEN
    SELECT status INTO t_status FROM cm.templates WHERE template_id = NEW.template_id;
    IF t_status IS DISTINCT FROM 'approved' THEN
      RAISE EXCEPTION 'outbox: template % is not approved (%)', NEW.template_id, t_status
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION cm.outbox_body_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.body IS NOT NULL AND NEW.body IS DISTINCT FROM OLD.body THEN
    RAISE EXCEPTION 'outbox: body of % is frozen after authorisation (only purge to NULL)', OLD.outbox_id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS outbox_body_frozen_trg ON cm.outbox;
CREATE TRIGGER outbox_body_frozen_trg
  BEFORE UPDATE OF body ON cm.outbox
  FOR EACH ROW EXECUTE FUNCTION cm.outbox_body_frozen();
