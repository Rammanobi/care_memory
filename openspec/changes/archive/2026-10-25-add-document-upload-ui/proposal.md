## Why
Patients need to send photos and files of their papers to the care team, and doctors need to check what was read from them before anything enters the record.

## What Changes
- Patient app (Record > Documents): "Upload a document" card (camera and file picker), client checks (type, 10 MB), progress, calm results (sent, duplicate, plain-word errors), status pills on the documents list, Telugu strings (need native review). Mock mode fakes the upload.
- Doctor console (Requests): document cards with extracted fields, confidence pills, excerpt, a check-against-original line, Approve and Reject through the existing decideRequest call; toast for SSE `patient_document`.
- Out of scope: backend routes, a doctor "Download original" link (no route exists; TODO left in DocumentCard.tsx).
- Owning lane: H1 (web/), with the PatientApp pages. No change to cm/contracts/.
- Implements: patient-app and doctor-console specs.
