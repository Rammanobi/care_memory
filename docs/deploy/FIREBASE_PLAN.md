# CareMemory on Firebase Hosting + Firebase Authentication (deploy-time plan)

Status: design only, written 2026-10-25 from a read-only review of the repo. No Firebase, gcloud or
Google network call was made. Owner decision (2026-10-25): doctor, patient and family UIs are separate
**Firebase Hosting sites** in Firebase project `carememory` (Blaze, same GCP project as Cloud Run `cm-api`),
and sign-in uses the **Firebase Auth SDK**. OpenSpec: `add-firebase-hosting-auth`. Placeholders: `<domain>`,
`<project>` (= `carememory`), `<run-url>` (the `cm-api` `*.run.app` URL). Items marked VERIFY are Firebase
limits to confirm in the console/docs on the day; the plan has a fallback for each.

---

## 1. Hosting: one project, several sites

### 1.1 Sites and targets

| Site id (globally unique, VERIFY free) | Target | Lands on | Default URL (stage 1) | Custom host (stage 2) |
|---|---|---|---|---|
| `carememory-doctor` | `doctor` | `/doctor` | `carememory-doctor.web.app` | `doctor.<domain>` |
| `carememory-patient` | `patient` | `/patient` | `carememory-patient.web.app` | `patient.<domain>` |
| `carememory-family` | `family` | `/supporter` | `carememory-family.web.app` | `family.<domain>` |
| `carememory-demo` (optional) | `demo` | `/` (login chooser) | `carememory-demo.web.app` | `demo.<domain>` |

Create: `firebase hosting:sites:create carememory-doctor` (x4), then
`firebase target:apply hosting doctor carememory-doctor` (x4; writes `.firebaserc`).
**One build for all sites** (`web/dist`, `VITE_USE_MOCK=false`, `VITE_API_BASE=""`, `VITE_AUTH_MODE=firebase`):
the site only changes the landing redirect. A per-role build (`VITE_APP_AREA=patient` hiding doctor routes)
is a stage-2 hardening; the real gate is the API role check, not the bundle.

### 1.2 API route prefixes to rewrite to Cloud Run `cm-api`

Derived from every router in `cm/api/main.py` and every `http(...)`/XHR/EventSource call in `web/src`.

| Prefix (glob `"/x"` and `"/x/**"`) | Router | Called by web | Rewrite via Hosting |
|---|---|---|---|
| `/auth` | auth.py | yes (`/auth/me`; `/auth/login`,`/logout` only in local mode) | yes |
| `/review` | review.py | yes | yes |
| `/requests` | patient_requests.py | yes | yes |
| `/patients`, `/evidence`, `/notes`, `/lens`, `/messages` | patients.py | yes | yes |
| `/admin` (incl. `/admin/audit`, `/admin/usage/caps`) | admin.py, ops.py, patients.py | yes | yes |
| `/dashboard`, `/clinics` | dashboard.py | yes | yes |
| `/consents` | consent.py | yes | yes |
| `/templates` | templates.py | yes | yes |
| `/query` | query.py | yes | yes |
| `/portal` (incl. multipart `POST /portal/documents`) | portal.py, portal_answers.py | yes | yes |
| `/stream` (SSE) | stream.py | yes (EventSource) | **no**, see 1.4 |
| `/healthz`, `/readyz` | main.py | no | optional (smoke test) |
| `/webhooks/telegram`, `/tasks/*` | webhooks.py, tasks.py | no | **no**: Telegram and Cloud Tasks call `<run-url>` / cm-worker directly |

No collision with SPA areas: SPA uses `/`, `/doctor/*`, `/patient/*`, `/supporter`; API uses `/patients` (plural).
Rewrites are matched in order, so API rewrites go before the SPA fallback `"**" -> /index.html`.

### 1.3 `firebase.json` (shape; one entry per target, identical except the landing redirect)

```json
{ "hosting": [ { "target": "doctor", "public": "web/dist", "cleanUrls": true, "trailingSlash": false,
  "redirects": [ { "source": "/", "destination": "/doctor", "type": 302 } ],
  "rewrites": [
    { "source": "/auth{,/**}",   "run": { "serviceId": "cm-api", "region": "asia-south1" } },
    "... same for review requests patients evidence notes lens messages admin dashboard clinics consents templates query portal ...",
    { "source": "**", "destination": "/index.html" } ],
  "headers": [
    { "source": "/assets/**", "headers": [ { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" } ] },
    { "source": "**/*.html",  "headers": [ { "key": "Cache-Control", "value": "no-cache" } ] },
    { "source": "**", "headers": [ { "key": "X-Content-Type-Options", "value": "nosniff" },
      { "key": "Referrer-Policy", "value": "same-origin" }, { "key": "X-Frame-Options", "value": "DENY" },
      { "key": "Content-Security-Policy", "value": "default-src 'self'; connect-src 'self' https://<run-url> https://identitytoolkit.googleapis.com https://securetoken.googleapis.com; frame-ancestors 'none'" } ] } ] },
  "...patient, family, demo..." ] }
```

- API responses: the API must send `Cache-Control: private, no-store` (Hosting CDN only caches responses
  marked `public`, but set it explicitly so a mistake cannot cache PHI). Lane G adds a tiny middleware.
- Rewrite target: Hosting calls Cloud Run as an anonymous caller, so `cm-api` stays `--allow-unauthenticated`
  (already the case). VERIFY that Hosting rewrites support `asia-south1` (they support Cloud Run regions
  listed in the Hosting docs; if not, fallback: `VITE_API_BASE=<run-url>` + CORS, see 2.5).
- Host header: Cloud Run sees its own host or the site host; put `<run-url>` host, `*.web.app` site hosts and
  `*.<domain>` in `CM_ALLOWED_HOSTS` (VERIFY with one request in stage 1; log `host` and `x-forwarded-host`).
- Client IP: `request.client.host` becomes a Google proxy; nothing rate-limits on it in firebase mode
  (login is at Google), but logs should use the first `X-Forwarded-For` hop.
- Upload: `POST /portal/documents` through the rewrite. VERIFY the Hosting proxy body limit; the app limit
  (document size) must stay below it, else upload direct to `<run-url>`.

### 1.4 SSE `/stream` through Hosting: not supported, so bypass it

Hosting-to-Cloud-Run rewrites have a **60 s request timeout** and the CDN may buffer streamed bodies
(VERIFY), so `EventSource` through Hosting would at best reconnect every 60 s and at worst never deliver.
Also `EventSource` cannot send `Authorization`. Design:

| Option | How | Verdict |
|---|---|---|
| A. Polling only | `VITE_LIVE=poll`: `startLive` already polls every 5 s when SSE is down | **Stage 1** (zero risk, already tested) |
| B. fetch-based SSE reader, direct to Cloud Run | `fetch(<run-url>/stream?topics=..., {headers:{Authorization:Bearer}})`, read `res.body` stream, parse frames with existing `parseLive`; reconnect on token refresh; `VITE_STREAM_BASE=<run-url>`; CORS allows site origins + `Authorization`; cm-api `--timeout=3600` | **Stage 1b/2** (recommended) |
| C. Stream ticket | `POST /stream/ticket` -> 60 s single-use opaque ticket, `EventSource(<run-url>/stream?ticket=)` | Rejected: ticket in URL (logs), new table/state |

Polling stays as the safety net for B (30 s while connected), exactly as today.

### 1.5 Custom domains (stage 2)

Console: Hosting > each site > Add custom domain `doctor.<domain>` (etc.). Firebase shows the exact records;
expect a **TXT** ownership record and **A** record(s) to the Hosting IPs it lists (or CNAME to `<site>.web.app`
for subdomains, per console). Remove old A/AAAA records pointing at the LB IP from DEPLOY_PLAN.md; CAA must
allow `pki.goog` and `letsencrypt.org` (Hosting may use either). Certs are provisioned per host (minutes to
24 h); the `*.web.app` URLs keep working, so stage 1 never waits on DNS. Add every custom host to Firebase
Auth **Authorized domains**.

---

## 2. Authentication: Firebase Auth email/password, bearer tokens

### 2.1 Dual mode `AUTH_MODE=local|firebase` (default `local`)

| | `local` (dev, all existing tests) | `firebase` (Hosting deploy) |
|---|---|---|
| Sign-in | `POST /auth/login`, scrypt, `cm_session` HS256 cookie (`JWT_SIGNING_KEY`) | Web SDK `signInWithEmailAndPassword` |
| Credential to API | cookie (or bearer) | `Authorization: Bearer <Firebase ID token>` only |
| `/auth/login` | unchanged | 404/410 (`code=use_firebase`) |
| `/auth/logout` | clears cookie | no-op 204; client calls `signOut()` |
| CSRF `X-CM-Client` | required with cookie | not needed (no ambient credential); header kept harmless |

`current_user` in `cm/api/deps.py` branches once on the mode: local path is byte-for-byte unchanged.

### 2.2 Backend verification (`cm/api/firebase_auth.py`, pure, modelled on `cm/channels/gmail_oidc.py`)

`verify_firebase_token(token, project_id, key_fetcher, leeway_s=30, now=None)` fails closed:
header `alg == RS256` and `kid` known; keys from
`https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com` (x509 certs,
cached per process honouring `Cache-Control max-age`); `aud == <project>`;
`iss == https://securetoken.google.com/<project>`; `exp` future, `iat`/`auth_time` past; `sub` non-empty;
`firebase.sign_in_provider == "password"`. Reuses PyJWT + cryptography (already deps), injectable fetcher,
no network in tests. `firebase-admin` is **not** added to the API image (only to the admin script).

### 2.3 Claims and the DB cross-check (roles never trusted from the client)

Custom claims set only by the admin script (Admin SDK, server side): `role`, `pid` (person_id), `tv`
(token_version). After verifying the token, `current_user` runs the **same** SQL as today keyed by `pid`
and refuses (401 `unauthenticated`) unless: row exists, `auth_credentials.active`, `persons.role == role`,
`token_version == tv`. So a retired user, a role change, or a bumped `token_version` cuts access at once even
with a valid 1-hour ID token. Revoke = bump `token_version` + `revokeRefreshTokens(uid)` + reset claims.
Token without claims (e.g. a stray self-signup) -> 403 `no_role`. Optional stage 2: a nullable
`auth_credentials.firebase_uid` (lane A migration) checked against `sub`.

### 2.4 Web (`VITE_AUTH_MODE=firebase`)

- `web/src/auth/firebase.ts`: `initializeApp(config)` (public web config via `VITE_FIREBASE_*`, not a secret),
  `getAuth`, persistence `browserSessionPersistence` for doctor/admin (tab-scoped), local for patient (VERIFY UX).
- Login form keeps "username": email = `<username>@<VITE_AUTH_EMAIL_DOMAIN>` (e.g. `users.carememory.app`,
  never mailed). `signIn` -> `signInWithEmailAndPassword` -> `getMe()`; `signOut` -> `auth.signOut()`.
- `http.ts`: before each call `await auth.currentUser?.getIdToken()` (SDK refreshes within 5 min of expiry);
  on 401 retry once with `getIdToken(true)`, then sign out; `credentials: "omit"` in firebase mode.
- `uploadDocument.ts` (XHR): `setRequestHeader("Authorization", ...)`, `withCredentials=false`.
- `realtime/sse.ts`: option A then B (1.4); `onIdTokenChanged` restarts the stream.

### 2.5 Cookies, CORS, CSRF

Hosting forwards only the `__session` cookie to Cloud Run, so `cm_session` would be dropped: firebase mode
uses bearer tokens only and never sets a cookie. REST goes same-origin through the rewrite (no CORS). Direct
calls to `<run-url>` (`/stream`, fallbacks) need `CORS_ORIGINS` = the exact site origins
(`https://carememory-*.web.app`, `https://*.<domain>` listed one by one), `allow_headers` already includes
`Authorization`; set `allow_credentials=False` in firebase mode. CSRF: no ambient credential, so no CSRF;
XSS becomes the main token-theft path (CSP header in 1.3, no `dangerouslySetInnerHTML`).

### 2.6 Demo accounts (`scripts/firebase_users.py`, design only)

Runs on the owner's machine with Application Default Credentials (`gcloud auth application-default login`),
`firebase-admin` from `requirements-dev.txt`. For each of `dr.rao`, `admin.demo`, `demo.pt0906`,
`demo.pt0960`, `ravi.pt0142`, `lakshmi.s01`: read password from Secret Manager `DEMO_USER_PASSWORDS` (JSON,
in memory only); look up `person_id`, `role`, `token_version` in Cloud SQL (via the proxy) or from a
`--from-seed` export; `create_user` or `update_user(email, password, email_verified=True, disabled=False)`;
`set_custom_user_claims({role, pid, tv})`. Idempotent; prints only `username: created|updated|claims ok`;
`--dry-run`; refuses to run if a password is under 12 chars; `--revoke <username>` path. Never logs or
echoes passwords, never writes them to disk.

---

## 3. Security review

| Risk | Mitigation |
|---|---|
| Open self-signup creates accounts | Disable "Enable create (sign-up)" (Auth > Settings > User actions; VERIFY it is available, else upgrade to Identity Platform, free tier). Backend also refuses tokens without claims/DB row |
| Role escalation | Claims settable only with Admin SDK; backend recomputes role from `cm.persons` and requires equality |
| Token theft (XSS, shared kiosk) | 1 h ID tokens; session persistence for staff; CSP; revoke via `tv` bump + refresh-token revoke; Firebase sign-out on shared devices |
| Disabled/retired user keeps a valid token | DB check per request (`active`, `tv`); `disabled=True` in Firebase blocks refresh |
| Forged token / wrong project | RS256 only, pinned `aud`/`iss`, kid must be in Google's set; fail closed |
| Brute force | Firebase built-in throttling; enable email-enumeration protection; strong generated passwords |
| Unknown origins using the config | Authorized domains = only the site and custom hosts (+ `localhost` only in a dev project); optional App Check (reCAPTCHA Enterprise) stage 2 |
| PHI cached by CDN | API `Cache-Control: private, no-store`; no API path under `public` headers |
| Webhook/task routes exposed via Hosting | Not rewritten; they stay on `<run-url>` with their own secrets/OIDC |
| PII to Google Identity | Firebase stores only synthetic email + uid + claims (no names, phone, diagnosis); demo data is synthetic (`CM_DATA_CLASS` mock/synthetic). For real data (DPDP Act 2023): processor terms, India data residency of Auth (global service, VERIFY), notice in `docs/dpdp_notice_v1.md`, erasure = delete Firebase user + identity vault row |
| Mode confusion | Startup refuses `AUTH_MODE=firebase` without `FIREBASE_PROJECT_ID`; `CM_ENV=prod` with `AUTH_MODE=local` logs a warning |

---

## 4. Lanes, files, effort

| # | Lane | Files (exclusive) | Work | Size | Stage |
|---|---|---|---|---|---|
| T1 | I | `firebase.json`, `.firebaserc`, `infra/firebase/README.md`, `infra/env/api.env.yaml` | sites, targets, rewrites, headers; env `AUTH_MODE`, `FIREBASE_PROJECT_ID`, `CORS_ORIGINS`, `CM_ALLOWED_HOSTS` | S (1 h) | 1 |
| T2 | G | `cm/api/firebase_auth.py`, `tests/api/test_firebase_auth.py` | pure verifier + key fetcher, tests with a local RSA key | M (2 h) | 1 |
| T3 | G | `cm/api/deps.py`, `cm/api/routers/auth.py`, `cm/core/config.py` (A owns; RFC-free env read, coordinate) | `AUTH_MODE` branch, claim/DB cross-check, login 404 in firebase mode, `no-store` middleware in `main.py` | M (2 h) | 1 |
| T4 | H1 | `web/src/auth/{session.tsx,firebase.ts}`, `web/src/api/{http.ts,uploadDocument.ts}`, `package.json` (`firebase`) | SDK sign-in, bearer, refresh/401 retry, sign-out; tests with a fake auth | M (2-3 h) | 1 |
| T5 | H1 | `web/src/realtime/sse.ts` | `VITE_LIVE=poll` (stage 1); fetch-SSE reader with bearer (1b) | S + M | 1/1b |
| T6 | I | `scripts/firebase_users.py`, `requirements-dev.txt` | demo users + claims via ADC | S-M (1.5 h) | 1 |
| T7 | I + owner | DNS, console | custom domains, authorized domains | S (+ cert wait) | 2 |
| T8 | A (optional) | migration `auth_credentials.firebase_uid` | uid pinning | S | 2 |

T1, T2, T4, T6 run in parallel; T3 after T2; integration smoke after all. **Stage 1 about 3-4 h wall clock**
with 3 lanes; stage 2 about 1 h work + DNS/cert wait (minutes to 24 h).

## 5. Owner inputs (no secrets in chat)

- [ ] Confirm Firebase project `carememory` is the GCP project hosting `cm-api` (Blaze).
- [ ] Console: Authentication > Get started > enable **Email/Password** (not passwordless).
- [ ] Console: Authentication > Settings > User actions: **disable sign-up** (and delete); enable email-enumeration protection.
- [ ] Console: Authentication > Settings > Authorized domains: add the four `*.web.app` sites; later the custom hosts; remove unused.
- [ ] Console: Project settings > add a Web app; give the agent the public web config **names** set in `web/.env.production` (apiKey here is public by design, still not pasted in chat).
- [ ] `npm i -g firebase-tools`, `firebase login`, `gcloud auth application-default login` on the deploy machine.
- [ ] Choose site ids (if `carememory-*` are taken) and `VITE_AUTH_EMAIL_DOMAIN`.
- [ ] Stage 2: domain `<domain>`, registrar access to add the TXT/A records Firebase shows.

## 6. Ordered runbook

1. Owner console steps (5) and CLI logins. 2. Land T1-T6, `make check` green in `AUTH_MODE=local`.
3. Deploy `cm-api` (DEPLOY_PLAN.md 2.x) with `AUTH_MODE=firebase`, `FIREBASE_PROJECT_ID`, `--timeout=3600`.
4. `python scripts/firebase_users.py --dry-run`, then without. 5. `npm run build` (firebase env) in `web/`.
6. `firebase hosting:sites:create` x4, `firebase target:apply` x4.
7. `firebase hosting:channel:deploy preview --only hosting:doctor` (preview URL), smoke, then
   `firebase deploy --only hosting`. 8. Smoke per site: login per role, wrong-role site redirect, approve a card,
   patient upload, `/healthz` via rewrite, disabled user refused, token without claims refused.
9. Stage 2: custom domains + authorized domains, CORS/hosts env update, redeploy `cm-api`.

**Rollback:** `firebase hosting:rollback` per site (or re-deploy previous release in console); API:
`AUTH_MODE=local` + previous Cloud Run revision (`update-traffic`) and serve the SPA from `cm-api` itself
(`mount_spa`, still in the image) on `<run-url>`; users: `firebase_users.py --revoke`. Local stack unchanged.

## 7. Changes to DEPLOY_PLAN.md

| Stays | Replaced / dropped |
|---|---|
| Cloud Run `cm-api`, `cm-worker`, Cloud Run Jobs (migrate, seed) | Global external LB, static IP, serverless NEG, `infra/85_lb.sh`, `infra/lb/urlmap.yaml`, managed cert (G16, LB cost line in section 4) |
| Cloud SQL `cm-pg`, Secret Manager, Cloud Tasks queues, Cloud Scheduler, Pub/Sub | LB host-based landing redirects (now per-site `redirects` in `firebase.json`) |
| Telegram webhook + task routes on `<run-url>` / worker | Cookie domain design (1.6): no session cookie in firebase mode; `CM_COOKIE_DOMAIN`, `COOKIE_SECURE` only matter for local mode |
| `mount_spa` in the image (fallback serving on `<run-url>`) | DNS A records to the LB IP (now Firebase-provided TXT/A per host) |
| SSE `--timeout=3600` on cm-api (G17) | `JWT_SIGNING_KEY` no longer used in firebase mode (kept for local mode and tests) |
