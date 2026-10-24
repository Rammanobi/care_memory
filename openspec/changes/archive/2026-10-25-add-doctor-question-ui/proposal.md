## Why
Patients now ask questions through Telegram and the app, and the backend prepares research and a suggested reply for the doctor. The console must show these questions live, let the doctor answer with an edited reply, and let the patient see a calm status and the reply.

## What Changes
- Doctor: a live notification (toast, unread badge on Requests, tab title count, optional sound, urgent toasts stay until opened) on the SSE `review` event `kind: patient_question`.
- Doctor Requests page: patient question cards (channel, category, urgency, waiting time with SLA colours, research panel pending/ready/failed with citation chips, editable reply, banned-word hint, server refusal shown plainly, sent-to channel line, keyboard shortcuts).
- Patient app: status pill "Waiting for your doctor" / "Your doctor replied", reply text with "In reply to your question" quote, replies threaded in Messages. Research and internal fields are never mapped to patient screens. Telugu strings added (need native review).
- Mock mode: three sample questions (ready, pending, failed) and an optional `?notify` demo event.
- Wire mapping of `data.research`, `data.origin`, portal `status` waiting|answered and `in_reply_to`.

## Out of scope
Backend routes and events (another agent), Telegram, `cm/`, Dockerfile, infra.

## Owning lane and spec
Lane H1 (web shell and ReviewQueue) with the PatientApp pages; implements specs `doctor-console` and `patient-app`. No change to `cm/contracts/`.
