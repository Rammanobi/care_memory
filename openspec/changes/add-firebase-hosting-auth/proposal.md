# add-firebase-hosting-auth

## Why
Owner decision (2026-10-25): at deploy time the doctor, patient and family (Supporter) UIs are hosted as
separate Firebase Hosting sites in Firebase project `carememory` (Blaze, same GCP project as Cloud Run
`cm-api`), and sign-in uses Firebase Authentication. This replaces the global load balancer, serverless NEG,
managed certificate and host-only session cookie design of `add-gcp-cloud-run-deploy`. Hosting forwards only
the `__session` cookie to Cloud Run, so the API must accept Firebase ID tokens as bearer tokens.

## What Changes
- Firebase Hosting multi-site config (`firebase.json`, `.firebaserc`): sites doctor, patient, family, demo
  (optional); API prefixes rewritten to Cloud Run `cm-api`; SPA fallback; cache and security headers.
- `/stream` (SSE) is not proxied through Hosting (60 s cap, buffering): stage 1 polls, stage 1b uses a
  fetch-based SSE reader with a bearer token directly against the Cloud Run URL.
- New env `AUTH_MODE=local|firebase` (default `local`, all existing tests unchanged).
- Backend verifies Firebase ID tokens (RS256, Google securetoken keys, pinned `aud`/`iss`) in a pure verifier
  modelled on `cm/channels/gmail_oidc.py`; custom claims `role`, `pid`, `tv` are cross-checked against
  `cm.persons` / `cm.auth_credentials` (active, role, token_version) on every request.
- Web uses the Firebase Web SDK: sign-in, `getIdToken()` bearer on every call and on upload, refresh, sign-out.
- Admin script creates the six demo Firebase users with custom claims via Application Default Credentials;
  passwords come from Secret Manager and are never printed.
- `/auth/login` is disabled in firebase mode; API responses send `Cache-Control: private, no-store`.

Design document: `docs/deploy/FIREBASE_PLAN.md`.

## Out of scope
- Social / phone / passwordless sign-in, self-signup (disabled), App Check enforcement (optional, stage 2).
- Real patient data (stays `CM_DATA_CLASS` mock/synthetic); DPDP processor review for real data.
- Changes to `cm/contracts/` (none needed: `Me` and `TokenOut` are unchanged; no RFC).

## Owning lanes
I (Hosting config, env, demo-user script), G (verifier, `current_user` branch, auth router, no-store
middleware), H1 (web auth, http adapter, upload, realtime), A (optional `firebase_uid` migration, config read
of `AUTH_MODE`/`FIREBASE_PROJECT_ID`).

## Spec sections
INTEGRATION_DECISIONS a5 (auth); `docs/deploy/DEPLOY_PLAN.md` 1.2-1.6 (superseded parts listed in
FIREBASE_PLAN.md section 7).
