-- 0008_event_stream.sql (slice RFC-S2): LISTEN/NOTIFY feed for GET /stream.
-- Triggers publish a tiny JSON on channel cm_events when a row is created or decided. NOTIFY is
-- delivered on commit. Payload carries ids only, never text.
CREATE OR REPLACE FUNCTION cm.notify_event() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  ev_type text;
  topic text := 'review';
  ref uuid;
  pid uuid;
  person uuid;
BEGIN
  IF TG_TABLE_NAME = 'approvals' THEN
    ev_type := CASE WHEN COALESCE(NEW.payload->>'subkind','') = 'patient_request'
                    THEN 'request_created' ELSE 'approval_created' END;
    ref := NEW.approval_id; pid := NEW.patient_id;
  ELSIF TG_TABLE_NAME = 'review_decisions' THEN
    ev_type := 'approval_decided';
    ref := NEW.approval_id;
    SELECT patient_id INTO pid FROM cm.approvals WHERE approval_id = NEW.approval_id;
  ELSE
    IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN RETURN NEW; END IF;
    IF TG_OP = 'UPDATE' AND NEW.status NOT IN ('sent','failed') THEN RETURN NEW; END IF;
    ev_type := 'message_sent'; topic := 'channels'; ref := NEW.outbox_id; person := NEW.recipient_id;
  END IF;
  IF pid IS NOT NULL AND person IS NULL THEN
    SELECT person_id INTO person FROM cm.patients WHERE patient_id = pid;
  END IF;
  PERFORM pg_notify('cm_events', json_build_object(
    'type', ev_type, 'topic', topic, 'ref', ref, 'patient_id', pid, 'person_id', person)::text);
  RETURN NEW;
END
$fn$;

DROP TRIGGER IF EXISTS approvals_notify ON cm.approvals;
CREATE TRIGGER approvals_notify AFTER INSERT ON cm.approvals
  FOR EACH ROW EXECUTE FUNCTION cm.notify_event();
DROP TRIGGER IF EXISTS decisions_notify ON cm.review_decisions;
CREATE TRIGGER decisions_notify AFTER INSERT ON cm.review_decisions
  FOR EACH ROW EXECUTE FUNCTION cm.notify_event();
DROP TRIGGER IF EXISTS outbox_notify ON cm.outbox;
CREATE TRIGGER outbox_notify AFTER INSERT OR UPDATE OF status ON cm.outbox
  FOR EACH ROW EXECUTE FUNCTION cm.notify_event();
